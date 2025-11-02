from flask_jwt_extended import jwt_required

from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import user_service, tasks_service, schedule_service
from zou.app.utils import permissions
from zou.app.services.exception import WrongParameterException


class ProductionScheduleVersionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, options=None):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        if "project_id" in options.keys():
            return user_service.check_project_access(options["project_id"])
        else:
            return permissions.check_admin_permissions()

    @jwt_required()
    def get(self):
        """
        Get production schedule versions
        ---
        tags:
          - Crud
        description: Retrieve all production schedule versions. Supports
          filtering via query parameters and pagination. Vendor and
          client access is blocked. Requires project access or admin
          permissions.
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
          - in: query
            name: project_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter by project ID
        responses:
            200:
              description: Production schedule versions retrieved successfully
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
        Create production schedule version
        ---
        tags:
          - Crud
        description: Create a new production schedule version with data
          provided in the request body. JSON format is expected.
          Requires manager access to the project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - project_id
                properties:
                  name:
                    type: string
                    example: Schedule Version 1
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Production schedule version created successfully
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
                        example: Schedule Version 1
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
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

    def check_create_permissions(self, data):
        return user_service.check_manager_project_access(
            project_id=data["project_id"]
        )


class ProductionScheduleVersionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, instance_dict):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return user_service.check_project_access(instance_dict["project_id"])

    @jwt_required()
    def get(self, instance_id):
        """
        Get production schedule version
        ---
        tags:
          - Crud
        description: Retrieve a production schedule version by its ID
          and return it as a JSON object. Supports including relations.
          Vendor and client access is blocked. Requires project access.
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
              description: Production schedule version retrieved successfully
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
                        example: Schedule Version 1
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
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
        Update production schedule version
        ---
        tags:
          - Crud
        description: Update a production schedule version with data
          provided in the request body. JSON format is expected.
          Requires manager access to the project.
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
                    example: Updated Schedule Version 1
        responses:
            200:
              description: Production schedule version updated successfully
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
                        example: Updated Schedule Version 1
                      project_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
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
        Delete production schedule version
        ---
        tags:
          - Crud
        description: Delete a production schedule version by its ID.
          Returns empty response on success.
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
              description: Production schedule version deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def check_update_permissions(self, instance_dict, data):
        return user_service.check_manager_project_access(
            project_id=instance_dict["project_id"]
        )


class ProductionScheduleVersionTaskLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersionTaskLink)

    def check_read_permissions(self, options=None):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        if "project_id" in options.keys():
            return user_service.check_project_access(options["project_id"])
        else:
            return permissions.check_admin_permissions()

    @jwt_required()
    def get(self):
        """
        Get production schedule version task links
        ---
        tags:
          - Crud
        description: Retrieve all production schedule version task
          links. Supports filtering via query parameters and pagination.
          Vendor and client access is blocked. Requires project access
          or admin permissions.
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
          - in: query
            name: project_id
            required: false
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter by project ID
        responses:
            200:
              description: Task links retrieved successfully
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
        Create production schedule version task link
        ---
        tags:
          - Crud
        description: Create a link between a production schedule version
          and a task. JSON format is expected. Task and schedule version
          must be in the same project. Requires manager access to the
          project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - production_schedule_version_id
                  - task_id
                properties:
                  production_schedule_version_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Task link created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      production_schedule_version_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or task and schedule version not in same project
        """
        return super().post()

    def check_create_permissions(self, data):
        project_id_from_production_version_schedule = (
            schedule_service.get_production_schedule_version(
                data["production_schedule_version_id"]
            )["project_id"]
        )
        project_id_from_task = tasks_service.get_task(data["task_id"])[
            "project_id"
        ]
        if project_id_from_production_version_schedule != project_id_from_task:
            raise WrongParameterException(
                "The task and the production schedule version must be in the same project."
            )
        return user_service.check_manager_project_access(
            project_id=project_id_from_production_version_schedule
        )


class ProductionScheduleVersionTaskLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProductionScheduleVersionTaskLink)
        self.protected_fields = [
            "id",
            "created_at",
            "updated_at",
            "task_id",
            "production_schedule_version_id",
        ]

    def check_read_permissions(self, instance_dict):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_project_access(task["project_id"])

    @jwt_required()
    def get(self, instance_id):
        """
        Get production schedule version task link
        ---
        tags:
          - Crud
        description: Retrieve a production schedule version task link
          by its ID and return it as a JSON object. Supports including
          relations. Vendor and client access is blocked. Requires
          project access.
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
              description: Task link retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      production_schedule_version_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
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
        Update production schedule version task link
        ---
        tags:
          - Crud
        description: Update a production schedule version task link
          with data provided in the request body. JSON format is
          expected. Protected fields cannot be changed. Requires
          manager access to the project.
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
                properties: {}
        responses:
            200:
              description: Task link updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      production_schedule_version_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      task_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
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
        Delete production schedule version task link
        ---
        tags:
          - Crud
        description: Delete a production schedule version task link
          by its ID. Returns empty response on success. Requires
          manager access to the project.
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
              description: Task link deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    def check_update_permissions(self, instance_dict, data):
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_manager_project_access(
            project_id=task["project_id"]
        )

    def check_delete_permissions(self, instance_dict):
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_manager_project_access(
            project_id=task["project_id"]
        )
