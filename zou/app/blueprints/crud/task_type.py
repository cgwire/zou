from flask_jwt_extended import jwt_required

from zou.app.models.task_type import TaskType
from zou.app.services.exception import WrongParameterException
from zou.app.services import tasks_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class TaskTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskType)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get task types
        ---
        tags:
          - Crud
        description: Retrieve all task types. Supports filtering via
          query parameters and pagination.
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
              description: Task types retrieved successfully
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
        Create task type
        ---
        tags:
          - Crud
        description: Create a new task type with data provided in the
          request body. JSON format is expected. Task type names must
          be unique.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - for_entity
                properties:
                  name:
                    type: string
                    example: Animation
                  for_entity:
                    type: string
                    example: Shot
                  color:
                    type: string
                    example: "#FF5733"
        responses:
            201:
              description: Task type created successfully
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
                        example: Animation
                      for_entity:
                        type: string
                        example: Shot
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
              description: Invalid data format or task type name already exists
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        name = data.get("name", None)
        task_type = TaskType.get_by(name=name)
        if task_type is not None:
            raise WrongParameterException(
                "A task type with similar name already exists"
            )
        return data

    def post_creation(self, instance):
        tasks_service.clear_task_type_cache(str(instance.id))
        return instance.serialize()


class TaskTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get task type
        ---
        tags:
          - Crud
        description: Retrieve a task type by its ID and return it as a
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
              description: Task type retrieved successfully
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
                        example: Animation
                      for_entity:
                        type: string
                        example: Shot
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
        Update task type
        ---
        tags:
          - Crud
        description: Update a task type with data provided in the
          request body. JSON format is expected. Task type names must
          be unique.
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
                    example: Updated Animation
                  color:
                    type: string
                    example: "#FF5734"
        responses:
            200:
              description: Task type updated successfully
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
                        example: Updated Animation
                      for_entity:
                        type: string
                        example: Shot
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
              description: Invalid data format or task type name already exists
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete task type
        ---
        tags:
          - Crud
        description: Delete a task type by its ID. Returns empty
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
              description: Task type deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        name = data.get("name", None)
        if name is not None:
            task_type = TaskType.get_by(name=name)
            if task_type is not None and instance_id != str(task_type.id):
                raise WrongParameterException(
                    "A task type with similar name already exists"
                )
        return data

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict
