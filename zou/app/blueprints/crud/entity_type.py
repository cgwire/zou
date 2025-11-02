from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.models.entity_type import EntityType
from zou.app.utils import events
from zou.app.services import entities_service, assets_service

from zou.app.services.exception import WrongParameterException


class EntityTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityType)

    @jwt_required()
    def get(self):
        """
        Get entity types
        ---
        tags:
          - Crud
        description: Retrieve all entity types. Supports filtering via query
          parameters and pagination.
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
              description: Entity types retrieved successfully
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
        Create entity type
        ---
        tags:
          - Crud
        description: Create a new entity type with data provided in the
          request body. JSON format is expected. Entity type names must
          be unique.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                properties:
                  name:
                    type: string
                    example: Character
                  color:
                    type: string
                    example: "#FF5733"
        responses:
            201:
              description: Entity type created successfully
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
                        example: Character
                      color:
                        type: string
                        example: "#FF5733"
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or entity type already exists
        """
        return super().post()

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return [
            asset_type.serialize(relations=relations)
            for asset_type in query.all()
        ]

    def check_read_permissions(self, options=None):
        return True

    def emit_create_event(self, instance_dict):
        events.emit("asset-type:new", {"asset_type_id": instance_dict["id"]})

    def post_creation(self, instance):
        assets_service.clear_asset_type_cache()
        return instance.serialize(relations=True)

    def check_creation_integrity(self, data):
        entity_type = EntityType.query.filter(
            EntityType.name.ilike(data.get("name", ""))
        ).first()
        if entity_type is not None:
            raise WrongParameterException(
                "Entity type with this name already exists"
            )
        return data


class EntityTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get entity type
        ---
        tags:
          - Crud
        description: Retrieve an entity type by its ID and return it as a
          JSON object. Supports including relations.
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
              description: Entity type retrieved successfully
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
                        example: Character
                      color:
                        type: string
                        example: "#FF5733"
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
    def put(self, instance_id):
        """
        Update entity type
        ---
        tags:
          - Crud
        description: Update an entity type with data provided in the
          request body. JSON format is expected.
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
                    example: Updated Character
                  color:
                    type: string
                    example: "#FF5734"
        responses:
            200:
              description: Entity type updated successfully
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
                        example: Updated Character
                      color:
                        type: string
                        example: "#FF5734"
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete entity type
        ---
        tags:
          - Crud
        description: Delete an entity type by its ID. Returns empty
          response on success.
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
              description: Entity type deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def emit_update_event(self, instance_dict):
        events.emit(
            "asset-type:update", {"asset_type_id": instance_dict["id"]}
        )

    def emit_delete_event(self, instance_dict):
        events.emit(
            "asset-type:delete", {"asset_type_id": instance_dict["id"]}
        )

    def post_update(self, instance_dict, data):
        entities_service.clear_entity_type_cache(instance_dict["id"])
        assets_service.clear_asset_type_cache()
        instance_dict["task_types"] = [
            str(task_types.id) for task_types in self.instance.task_types
        ]
        return instance_dict

    def post_delete(self, instance_dict):
        entities_service.clear_entity_type_cache(instance_dict["id"])
        assets_service.clear_asset_type_cache()
        return instance_dict
