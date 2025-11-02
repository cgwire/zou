from flask_jwt_extended import jwt_required

from zou.app.models.task_status import TaskStatus
from zou.app.services import tasks_service
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class TaskStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskStatus)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    def get(self):
        """
        Get task statuses
        ---
        tags:
          - Crud
        description: Retrieve all task statuses. Supports filtering via
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
              description: Task statuses retrieved successfully
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
        Create task status
        ---
        tags:
          - Crud
        description: Create a new task status with data provided in the
          request body. JSON format is expected. If is_default is true,
          sets all other statuses to non-default.
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
                    example: To Do
                  short_name:
                    type: string
                    example: TODO
                  color:
                    type: string
                    example: "#FF5733"
                  is_default:
                    type: boolean
                    default: false
                    example: false
        responses:
            201:
              description: Task status created successfully
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
                        example: To Do
                      short_name:
                        type: string
                        example: TODO
                      color:
                        type: string
                        example: "#FF5733"
                      is_default:
                        type: boolean
                        example: false
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

    def post_creation(self, instance):
        tasks_service.clear_task_status_cache(str(instance.id))
        return instance.serialize()

    def check_creation_integrity(self, data):
        if data.get("is_default", False):
            status = TaskStatus.get_by(is_default=True)
            if status:
                status.update({"is_default": False})
        return data


class TaskStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskStatus)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get task status
        ---
        tags:
          - Crud
        description: Retrieve a task status by its ID and return it as a
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
              description: Task status retrieved successfully
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
                        example: To Do
                      short_name:
                        type: string
                        example: TODO
                      color:
                        type: string
                        example: "#FF5733"
                      is_default:
                        type: boolean
                        example: false
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
        Update task status
        ---
        tags:
          - Crud
        description: Update a task status with data provided in the
          request body. JSON format is expected. If is_default is set
          to true, sets all other statuses to non-default.
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
                    example: In Progress
                  short_name:
                    type: string
                    example: WIP
                  color:
                    type: string
                    example: "#00FF00"
                  is_default:
                    type: boolean
                    example: true
        responses:
            200:
              description: Task status updated successfully
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
                        example: In Progress
                      short_name:
                        type: string
                        example: WIP
                      color:
                        type: string
                        example: "#00FF00"
                      is_default:
                        type: boolean
                        example: true
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
        Delete task status
        ---
        tags:
          - Crud
        description: Delete a task status by its ID. Returns empty
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
              description: Task status deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def pre_update(self, instance_dict, data):
        if data.get("is_default", False):
            status = TaskStatus.get_by(is_default=True)
            if status:
                status.update({"is_default": False})
        return instance_dict

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict
