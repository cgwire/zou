import copy
import re

from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
    build_db_error_message,
)
from zou.app.exceptions import WrongParameterException
from zou.app.models.entity import ENTITY_STATUSES, Entity
from zou.app.services import (
    assets_service,
    breakdown_service,
    concepts_service,
    edits_service,
    entities_service,
    entity_types_service,
    index_service,
    permissions_service,
    persons_service,
    shots_service,
    user_service,
)
from zou.app.utils import date_helpers, events, fields, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/entity.yml")

# A shot version takes the next change of its author for up to one minute after
# its last change, and up to five minutes after its creation, if that change
# fits: see EntityResource.get_recent_version.
SHOT_VERSION_FOLD_DELAY = 60
SHOT_VERSION_FOLD_MAX_DURATION = 5 * 60


class EntityEventMixin(object):
    def emit_event(self, event_name, entity_dict):
        instance_id = entity_dict["id"]
        type_name = entity_types_service.get_base_entity_type_name(entity_dict)
        # The update route clears the cache itself.
        if event_name == "delete":
            self.clear_entity_type_cache(entity_dict)
        # ConceptFolder gives concept-folder:update and concept_folder_id. The
        # concept folder routes emit these names.
        words = [word.lower() for word in re.findall("[A-Z][a-z]*", type_name)]
        events.emit(
            f"{'-'.join(words)}:{event_name}",
            {f"{'_'.join(words)}_id": instance_id},
            project_id=entity_dict["project_id"],
        )

    def clear_entity_type_cache(self, entity_dict):
        entity_id = entity_dict["id"]
        if entity_types_service.is_shot(entity_dict):
            shots_service.clear_shot_cache(entity_id)
        elif entity_types_service.is_sequence(entity_dict):
            shots_service.clear_sequence_cache(entity_id)
        elif entity_types_service.is_edit(entity_dict):
            edits_service.clear_edit_cache(entity_id)
        elif entity_types_service.is_episode(entity_dict):
            shots_service.clear_episode_cache(entity_id)
        elif entity_types_service.is_concept(entity_dict):
            concepts_service.clear_concept_cache(entity_id)
        elif entity_types_service.is_asset_dict(entity_dict):
            assets_service.clear_asset_cache(entity_id)
        entities_service.clear_entity_cache(entity_id)


class EntitiesResource(BaseModelsResource, EntityEventMixin):
    def __init__(self):
        BaseModelsResource.__init__(self, Entity)

    def get_relations_eager_load(self):
        return [Entity.entities_out, Entity.instance_casting]

    def check_create_permissions(self, entity):
        permissions_service.check_manager_project_access(entity["project_id"])

    @jwt_required()
    @swag_from(SPECS["EntitiesResource_get"])
    def get(self):
        """
        Get entities
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["EntitiesResource_post"])
    def post(self):
        """
        Create entity
        """
        return super().post()

    def emit_create_event(self, entity_dict):
        self.emit_event("new", entity_dict)

    def check_read_permissions(self, options=None):
        return True

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            # Each entity uses the role of the user on its project.
            query = entities_service.filter_entities_by_projects(
                query,
                user_service.build_related_projects_filter(),
                user_service.get_project_ids_with_roles("vendor"),
            )
        return query

    def update_data(self, data):
        data = super().update_data(data)
        data["created_by"] = persons_service.get_current_user()["id"]
        return data

    def check_creation_integrity(self, data):
        """
        Make sure that the entity has a valid status.
        """
        if "status" in data:
            types = [entity_status for entity_status, _ in ENTITY_STATUSES]
            if data["status"] not in types:
                raise WrongParameterException("Invalid status")
        return True

    def all_entries(self, query=None, relations=False):
        entities = BaseModelsResource.all_entries(
            self, query=query, relations=relations
        )
        for entity in entities:
            entity["type"] = entity_types_service.get_base_entity_type_name(
                entity
            )
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
        entity["type"] = entity_types_service.get_base_entity_type_name(entity)
        return entity

    def check_read_permissions(self, entity):
        permissions_service.check_project_access(entity["project_id"])
        permissions_service.check_entity_access(entity["id"])

    def check_update_permissions(self, entity, data):
        return permissions_service.check_metadata_department_access(
            entity, data
        )

    def pre_update(self, instance_dict, data):
        """
        Make sure that the update does not violate the unique constraint
        on (name, project_id, entity_type_id, parent_id).
        """
        current_name = instance_dict.get("name")
        current_project_id = instance_dict.get("project_id")
        current_entity_type_id = instance_dict.get("entity_type_id")
        current_parent_id = instance_dict.get("parent_id")

        updated_name = data.get("name", current_name)
        updated_project_id = data.get("project_id", current_project_id)
        updated_entity_type_id = data.get(
            "entity_type_id", current_entity_type_id
        )
        updated_parent_id = data.get("parent_id", current_parent_id)

        if updated_parent_id == "" or updated_parent_id == "null":
            updated_parent_id = None
        if current_parent_id == "" or current_parent_id == "null":
            current_parent_id = None

        if (
            updated_name != current_name
            or updated_project_id != current_project_id
            or updated_entity_type_id != current_entity_type_id
            or updated_parent_id != current_parent_id
        ):
            if entities_service.is_entity_name_taken(
                updated_name,
                updated_project_id,
                updated_entity_type_id,
                updated_parent_id,
                instance_dict["id"],
            ):
                raise WrongParameterException(
                    f"An entity with name '{updated_name}', project_id '{updated_project_id}', "
                    f"entity_type_id '{updated_entity_type_id}', and parent_id '{updated_parent_id}' "
                    f"already exists. The combination of these fields must be unique."
                )

        return data

    @jwt_required()
    @swag_from(SPECS["EntityResource_get"])
    def get(self, instance_id):
        """
        Get entity
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["EntityResource_delete"])
    def delete(self, instance_id):
        """
        Delete entity
        """
        return super().delete(instance_id)

    def check_delete_permissions(self, entity):
        return permissions_service.check_entity_delete_access(entity)

    def pre_delete(self, entity):
        """
        Delete the links of the entity, and the subscriptions of a sequence,
        with no commit. The deletion of the entity commits these changes. If
        the database refuses the deletion (tasks, versions, child entities),
        it rolls them back.
        """
        entities_service.remove_entity_links_no_commit(entity)
        return entity

    @jwt_required()
    @swag_from(SPECS["EntityResource_put"])
    def put(self, instance_id):
        """
        Update entity
        """
        try:
            data = self.get_arguments()
            entity = self.get_model_or_404(instance_id)
            entity_dict = entity.serialize()
            self.check_update_permissions(entity_dict, data)
            self.pre_update(entity_dict, data)

            extra_data = copy.copy(entity.data) or {}
            if "data" not in data or data["data"] is None:
                data["data"] = {}
            extra_data.update(data["data"])
            data["data"] = extra_data

            previous_version = entity.serialize()
            data = self.update_data(data, instance_id)
            if data.get("source_id", None) == "null":
                data["source_id"] = None

            # Only a payload with ready_for can change it. Without this test,
            # each asset update calculated again the casting stats of all the
            # shots that use the asset.
            is_ready_for_changed = (
                "ready_for" in data
                and fields.serialize_value(entity.ready_for)
                != data["ready_for"]
            )

            entity.update(data)
            entity_dict = self.serialize_instance(entity)

            if entity_types_service.is_shot(entity_dict):
                index_service.remove_shot_index(entity_dict["id"])
                index_service.index_shot(entity)
                self.save_version_if_needed(entity_dict, previous_version)
            elif entity_types_service.is_edit(entity_dict):
                self.save_version_if_needed(entity_dict, previous_version)
            elif entity_types_service.is_asset(entity):
                index_service.remove_asset_index(entity_dict["id"])
                index_service.index_asset(entity)
                if is_ready_for_changed:
                    breakdown_service.refresh_casting_stats(entity_dict)
            self.clear_entity_type_cache(entity_dict)

            self.emit_update_event(entity_dict)
            return entity_dict, 200

        except StatementError as exception:
            # This block answers only malformed values. The application
            # handlers give all other errors (a permission refusal, a service
            # error) their own status, not a 400.
            current_app.logger.error(str(exception), exc_info=1)
            return (
                {"error": True, "message": build_db_error_message(exception)},
                400,
            )
        except TypeError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"error": True, "message": str(exception)}, 400

    def save_version_if_needed(self, shot, previous_shot):
        """
        If the frame range or the name of the given shot or edit changed,
        record a version of it. A client can send one update for each field
        or each keystroke (frame in, then frame out, a number typed slowly).
        Thus, such a series of updates by one person goes into one version
        with the final values: see get_recent_version.
        """
        frames = self.get_frame_range(shot.get("data"))
        previous_frames = self.get_frame_range(previous_shot.get("data"))
        version = None
        if frames != previous_frames or shot["name"] != previous_shot["name"]:
            person_id = persons_service.get_current_user()["id"]
            version = self.get_recent_version(shot, previous_shot, person_id)
            if version is None:
                version = shots_service.create_shot_version_raw(
                    shot["id"], previous_shot["name"], shot["data"], person_id
                )
            else:
                version.update({"data": shot["data"]})
        return version

    def get_frame_range(self, data):
        """
        Return the frame in and the frame out that a shot version records.
        """
        data = data or {}
        return data.get("frame_in", 0), data.get("frame_out", 0)

    def get_recent_version(self, shot, previous_shot, person_id):
        """
        Return the last version of the given shot if the last change of the
        given person can go into it. If not, return None. That version must:

        - have the given person as its author. If another person recorded the
          last version, the change does not go into an older version of the
          given person either. Thus the history stays in order.
        - have the frame values that this change does not set, as the shot
          had them. If this change sets the frame range, the version must
          also have the name that the shot had. A version recorded before a
          rename has the old name. A frame change in it would pair that name
          with a range that the shot never had under that name. A version
          recorded before a frame change by a route that records no version
          has the old value. If this change goes into it, the version gives
          that change to the given person. The function does not compare the
          values that this change sets. Thus a second rename goes into the
          version. A keystroke also goes into it when its request read the
          shot before the save of the previous keystroke.
        - have its last change at most one minute before, and its creation
          at most five minutes before. Only versions count: an update that
          recorded nothing does not make the window longer.
        """
        version = shots_service.get_last_shot_version_raw(shot["id"])
        if version is None or str(version.person_id) != str(person_id):
            return None
        frames = self.get_frame_range(shot.get("data"))
        previous_frames = self.get_frame_range(previous_shot.get("data"))
        version_frames = self.get_frame_range(version.data)
        if frames != previous_frames and version.name != previous_shot["name"]:
            return None
        for frame, previous_frame, version_frame in zip(
            frames, previous_frames, version_frames
        ):
            if frame == previous_frame and version_frame != previous_frame:
                return None
        updated_at = date_helpers.get_datetime_from_string(shot["updated_at"])
        last_changed_at = version.updated_at.replace(microsecond=0)
        created_at = version.created_at.replace(microsecond=0)
        if (
            date_helpers.get_date_diff(last_changed_at, updated_at)
            > SHOT_VERSION_FOLD_DELAY
            or date_helpers.get_date_diff(created_at, updated_at)
            > SHOT_VERSION_FOLD_MAX_DURATION
        ):
            return None
        return version

    def emit_update_event(self, entity_dict):
        self.emit_event("update", entity_dict)

    def emit_delete_event(self, entity_dict):
        self.emit_event("delete", entity_dict)

    def post_delete(self, entity_dict):
        if entity_types_service.is_asset_dict(entity_dict):
            index_service.remove_asset_index(entity_dict["id"])
        elif entity_types_service.is_shot(entity_dict):
            index_service.remove_shot_index(entity_dict["id"])

    def update_data(self, data, instance_id):
        """
        Make sure that the entity has a valid status.
        """
        data = super().update_data(data, instance_id)
        if "status" in data:
            types = [entity_status for entity_status, _ in ENTITY_STATUSES]
            if data["status"] not in types:
                raise WrongParameterException("Invalid status")
        return data
