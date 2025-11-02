import copy

from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import StatementError

from zou.app.models.entity import (
    Entity,
    EntityVersion,
    EntityLink,
    EntityConceptLink,
    ENTITY_STATUSES,
)
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
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
from zou.app.utils import date_helpers, events, permissions

from zou.app.services.exception import WrongParameterException

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

    @jwt_required()
    def get(self):
        """
        Get entities
        ---
        tags:
          - Crud
        description: Retrieve all entities. Supports filtering via query
          parameters and pagination. Includes project permission filtering
          for non-admin users.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Entities retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create entity
        ---
        tags:
          - Crud
        description: Create a new entity with data provided in the request
          body. JSON format is expected. Requires manager access to the
          project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - project_id
                  - entity_type_id
                properties:
                  name:
                    type: string
                    example: SH010
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_type_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  status:
                    type: string
                    example: running
                  data:
                    type: object
                    example: {"frame_in": 1001, "frame_out": 1120}
        responses:
            201:
              description: Entity created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: SH010
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_type_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      status:
                        type: string
                        example: running
                      data:
                        type: object
                        example: {"frame_in": 1001, "frame_out": 1120}
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().post()

    def emit_create_event(self, entity_dict):
        self.emit_event("new", entity_dict)

    def check_read_permissions(self, options=None):
        return True

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
            if permissions.has_vendor_permissions():
                query = query.join(Task).filter(
                    user_service.build_assignee_filter()
                )

        return query

    def update_data(self, data):
        data = super().update_data(data)
        data["created_by"] = persons_service.get_current_user()["id"]
        return data

    def check_creation_integrity(self, data):
        """
        Check if entity has a valid status.
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

    @jwt_required()
    def get(self, instance_id):
        """
        Get entity
        ---
        tags:
          - Crud
        description: Retrieve an entity by its ID and return it as a JSON
          object. Supports including relations. Requires project access.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Entity retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: SH010
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_type_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      status:
                        type: string
                        example: running
                      data:
                        type: object
                        example: {"frame_in": 1001, "frame_out": 1120}
                      type:
                        type: string
                        example: shot
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete entity
        ---
        tags:
          - Crud
        description: Delete an entity by its ID. Returns empty response
          on success. Can only be deleted by creator or project manager.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Entity deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

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
        Update entity
        ---
        tags:
          - Crud
        description: Update an entity with data provided in the request
          body. JSON format is expected. Supports shot versioning when
          frame data changes.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: SH010
                  data:
                    type: object
                    example: {"frame_in": 1001, "frame_out": 1120}
        responses:
            200:
              description: Entity updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: SH010
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      data:
                        type: object
                        example: {"frame_in": 1001, "frame_out": 1120}
            400:
              description: Invalid data format or validation error
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
            previous_updated_at = date_helpers.get_datetime_from_string(
                previous_shot["updated_at"]
            )
            updated_at = date_helpers.get_datetime_from_string(
                shot["updated_at"]
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

    def update_data(self, data, instance_id):
        """
        Check if the entity has a valid status.
        """
        data = super().update_data(data, instance_id)
        if "status" in data:
            types = [entity_status for entity_status, _ in ENTITY_STATUSES]
            if data["status"] not in types:
                raise WrongParameterException("Invalid status")
        return data
