import copy

from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import StatementError

from zou.app.models.entity import (
    Entity,
    EntityVersion,
    EntityLink,
    EntityConceptLink,
)
from zou.app.models.subscription import Subscription
from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    edits_service,
    index_service,
    persons_service,
    shots_service,
    user_service,
    concepts_service,
)
from zou.app.utils import events, fields, date_helpers

from werkzeug.exceptions import NotFound

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class EntityEventMixin(object):
    def emit_event(self, event_name, entity_dict):
        instance_id = entity_dict["id"]
        type_name = shots_service.get_base_entity_type_name(entity_dict)
        if event_name in ["update", "delete"]:
            if type_name == "shot":
                shots_service.clear_shot_cache(instance_id)
            if type_name == "asset":
                assets_service.clear_asset_cache(instance_id)
        events.emit(
            "%s:%s" % (type_name.lower(), event_name),
            {"%s_id" % type_name.lower(): instance_id},
            project_id=entity_dict["project_id"],
        )


class EntitiesResource(BaseModelsResource, EntityEventMixin):
    def __init__(self):
        BaseModelsResource.__init__(self, Entity)

    def check_create_permissions(self, entity):
        user_service.check_manager_project_access(entity["project_id"])

    def emit_create_event(self, entity_dict):
        self.emit_event("new", entity_dict)

    def update_data(self, data):
        data = super().update_data(data)
        data["created_by"] = persons_service.get_current_user()["id"]
        return data

    def all_entries(self, query=None, relations=False):
        entities = BaseModelsResource.all_entries(
            self, query=query, relations=relations
        )
        for entity in entities:
            entity["type"] = shots_service.get_base_entity_type_name(entity)
        return entities


class EntityResource(BaseModelResource, EntityEventMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Entity)
        self.protected_fields += [
            "instance_casting",
            "project_id",
            "entities_in",
            "entities_out",
            "type",
            "shotgun_id",
            "created_by",
        ]

    def serialize_instance(self, entity, relations=True):
        entity = entity.serialize(relations=relations)
        entity["type"] = shots_service.get_base_entity_type_name(entity)
        return entity

    def check_read_permissions(self, entity):
        user_service.check_project_access(entity["project_id"])
        user_service.check_entity_access(entity["id"])

    def check_update_permissions(self, entity, data):
        return user_service.check_metadata_department_access(entity, data)

    def check_delete_permissions(self, entity):
        return entity["created_by"] == persons_service.get_current_user()[
            "id"
        ] or user_service.check_manager_project_access(entity["project_id"])

    def pre_delete(self, entity):
        if shots_service.is_sequence(entity):
            Subscription.delete_all_by(entity_id=entity["id"])
        EntityLink.delete_all_by(entity_in_id=entity["id"])
        EntityLink.delete_all_by(entity_out_id=entity["id"])
        EntityConceptLink.delete_all_by(entity_in_id=entity["id"])
        EntityConceptLink.delete_all_by(entity_out_id=entity["id"])
        return entity

    @jwt_required()
    def put(self, instance_id):
        """
        Update a model with data given in the request body. JSON format is
        expected. Model performs the validation automatically when fields are
        modified.
        """
        try:
            data = self.get_arguments()
            entity = self.get_model_or_404(instance_id)
            self.check_update_permissions(entity.serialize(), data)

            extra_data = copy.copy(entity.data) or {}
            if "data" not in data or data["data"] is None:
                data["data"] = {}
            extra_data.update(data["data"])
            data["data"] = extra_data

            previous_version = entity.serialize()
            data = self.update_data(data, instance_id)
            if data.get("source_id", None) == "null":
                data["source_id"] = None

            is_ready_for_changed = str(entity.ready_for) != data.get(
                "ready_for", ""
            )

            entity.update(data)
            entity_dict = self.serialize_instance(entity)

            if shots_service.is_shot(entity_dict):
                index_service.remove_shot_index(entity_dict["id"])
                index_service.index_shot(entity)
                shots_service.clear_shot_cache(entity_dict["id"])
                self.save_version_if_needed(entity_dict, previous_version)
            elif shots_service.is_sequence(entity_dict):
                shots_service.clear_sequence_cache(entity_dict["id"])
            elif shots_service.is_edit(entity_dict):
                edits_service.clear_edit_cache(entity_dict["id"])
            elif shots_service.is_episode(entity_dict):
                shots_service.clear_episode_cache(entity_dict["id"])
            elif concepts_service.is_concept(entity_dict):
                concepts_service.clear_concept_cache(entity_dict["id"])
            elif assets_service.is_asset(entity):
                index_service.remove_asset_index(entity_dict["id"])
                index_service.index_asset(entity)
                if is_ready_for_changed:
                    breakdown_service.refresh_casting_stats(entity_dict)
                assets_service.clear_asset_cache(entity_dict["id"])
            entities_service.clear_entity_cache(entity_dict["id"])

            self.emit_update_event(entity_dict)
            return entity_dict, 200

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"error": True, "message": str(exception)}, 400
        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"error": True, "message": str(exception)}, 400
        except NotFound as exception:
            return {"error": True, "message": str(exception)}, 404
        except Exception as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"error": True, "message": str(exception)}, 400

    def save_version_if_needed(self, shot, previous_shot):
        previous_data = previous_shot.get("data", {}) or {}
        data = shot.get("data", {})
        frame_in = data.get("frame_in", 0)
        pframe_in = previous_data.get("frame_in", 0)
        frame_out = data.get("frame_in", 0)
        pframe_out = previous_data.get("frame_in", 0)
        name = data.get("name", "")
        pname = previous_shot["name"]
        version = None
        if frame_in != pframe_in or frame_out != pframe_out or name != pname:
            current_user_id = persons_service.get_current_user()["id"]
            previous_updated_at = fields.get_date_object(
                previous_shot["updated_at"], date_format="%Y-%m-%dT%H:%M:%S"
            )
            updated_at = fields.get_date_object(
                shot["updated_at"], date_format="%Y-%m-%dT%H:%M:%S"
            )
            if (
                date_helpers.get_date_diff(previous_updated_at, updated_at)
                > 60
            ):
                version = EntityVersion.create(
                    entity_id=shot["id"],
                    name=pname,
                    data=shot["data"],
                    person_id=current_user_id,
                )
        return version

    def emit_update_event(self, entity_dict):
        self.emit_event("update", entity_dict)

    def emit_delete_event(self, entity_dict):
        self.emit_event("delete", entity_dict)

    def post_delete(self, entity_dict):
        if assets_service.is_asset_dict(entity_dict):
            index_service.remove_asset_index(entity_dict["id"])
        elif shots_service.is_shot(entity_dict):
            index_service.remove_shot_index(entity_dict["id"])
