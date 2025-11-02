from flask import abort, current_app

from sqlalchemy.exc import StatementError
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.working_file import WorkingFile
from zou.app.services import user_service, files_service
from zou.app.utils import permissions


class WorkingFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, WorkingFile)

    def check_read_permissions(self, options=None):
        """
        Overriding so that people without admin credentials can still access
        this resource.
        """
        user_service.block_access_to_vendor()
        return True

    @jwt_required()
    def get(self):
        """
        Get working files
        ---
        tags:
          - Crud
        description: Retrieve all working files. Supports filtering via
          query parameters and pagination. Vendor access is blocked.
          Includes project permission filtering for non-admin users.
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
              description: Working files retrieved successfully
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
        Create working file
        ---
        tags:
          - Crud
        description: Create a new working file with data provided in the
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
                  - entity_id
                properties:
                  name:
                    type: string
                    example: work_file_v001
                  task_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  entity_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  revision:
                    type: integer
                    default: 1
                    example: 1
        responses:
            201:
              description: Working file created successfully
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
                        example: work_file_v001
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
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
        """
        Filtering to keep only the files from projects available to the user's
        team. Allows projects that are no longer open.
        """
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, WorkingFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_team_filter())
            )
            return query


class WorkingFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, WorkingFile)

    def check_read_permissions(self, instance):
        working_file = files_service.get_working_file(instance["id"])
        user_service.check_task_access(working_file["task_id"])
        return True

    def check_update_permissions(self, instance, data):
        working_file = files_service.get_working_file(instance["id"])
        user_service.check_task_action_access(working_file["task_id"])
        return True

    @jwt_required()
    def put(self, instance_id):
        """
        Update working file
        ---
        tags:
          - Crud
        description: Update a working file with data provided in the
          request body. JSON format is expected. Requires task action
          access.
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
                    example: updated_work_file_v001
                  revision:
                    type: integer
                    example: 2
        responses:
            200:
              description: Working file updated successfully
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
                        example: updated_work_file_v001
                      task_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      entity_id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
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

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete working file
        ---
        tags:
          - Crud
        description: Delete a working file by its ID. Returns empty
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
              description: Working file deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)

    @jwt_required()
    def get(self, instance_id):
        """
        Get working file
        ---
        tags:
          - Crud
        description: Retrieve a working file instance by its ID and return
          it as a JSON object.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Working file retrieved successfully
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
                        example: work_file_v001
                      task_id:
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
        try:
            working_file = files_service.get_working_file(instance_id)
            self.check_read_permissions(working_file)
            return self.clean_get_result(working_file)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

    def post_update(self, instance_dict, data):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_working_file_cache(instance_dict["id"])
        return instance_dict
