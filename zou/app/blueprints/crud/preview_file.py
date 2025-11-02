from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    user_service,
    tasks_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import deletion_service


class PreviewFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewFile)

    @jwt_required()
    def get(self):
        """
        Get preview files
        ---
        tags:
          - Crud
        description: Retrieve all preview files. Supports filtering via
          query parameters and pagination. Includes project permission
          filtering. Vendor users only see assigned tasks.
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
              description: Preview files retrieved successfully
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
        Create preview file
        ---
        tags:
          - Crud
        description: Create a new preview file with data provided in the
          request body. JSON format is expected.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - name
                  - task_id
                properties:
                  name:
                    type: string
                    example: preview_file_v001
                  task_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  revision:
                    type: integer
                    default: 1
                    example: 1
        responses:
            201:
              description: Preview file created successfully
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
                        example: preview_file_v001
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      revision:
                        type: integer
                        example: 1
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

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            query = (
                query.join(Task)
                .join(Project)
                .join(
                    ProjectStatus,
                    Project.project_status_id == ProjectStatus.id,
                )
                .filter(user_service.build_open_project_filter())
            )
            if permissions.has_vendor_permissions():
                query = query.filter(user_service.build_assignee_filter())
            else:
                query = query.filter(
                    user_service.build_related_projects_filter()
                )

        return query

    def check_read_permissions(self, options=None):
        return True


class PreviewFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewFile)

    def check_read_permissions(self, preview_file):
        """
        If it's a vendor, check if the user is working on the task.
        If it's an artist, check if preview file belongs to user projects.
        """
        if permissions.has_vendor_permissions():
            user_service.check_working_on_task(preview_file["task_id"])
        else:
            task = tasks_service.get_task(preview_file["task_id"])
            user_service.check_project_access(task["project_id"])
        return True

    @jwt_required()
    def get(self, instance_id):
        """
        Get preview file
        ---
        tags:
          - Crud
        description: Retrieve a preview file by its ID and return it as
          a JSON object. Supports including relations. Vendors must be
          working on the task. Artists must have project access.
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
              description: Preview file retrieved successfully
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
                        example: preview_file_v001
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      revision:
                        type: integer
                        example: 1
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
        Update preview file
        ---
        tags:
          - Crud
        description: Update a preview file with data provided in the
          request body. JSON format is expected. Requires project access.
          Non-managers must be working on the task.
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
                    example: updated_preview_file_v001
                  revision:
                    type: integer
                    example: 2
        responses:
            200:
              description: Preview file updated successfully
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
                        example: updated_preview_file_v001
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      revision:
                        type: integer
                        example: 2
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

    def check_update_permissions(self, preview_file, data):
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        if not permissions.has_manager_permissions():
            user_service.check_working_on_task(task["entity_id"])
        return True

    def check_delete_permissions(self, preview_file):
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_manager_project_access(task["project_id"])
        return True

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete preview file
        ---
        tags:
          - Crud
        description: Delete a preview file by its ID. Returns empty
          response on success. May require force flag if file has
          associated data.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: force
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Force deletion even if file has associated data
        responses:
            204:
              description: Preview file deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            deletion_service.remove_preview_file(
                instance, force=self.get_force()
            )
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204
