from flask_jwt_extended import jwt_required

from flask_restful import Resource


from zou.app.mixin import ArgsMixin
from zou.app.models.project import Project, PROJECT_STYLES
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    deletion_service,
    projects_service,
    shots_service,
    user_service,
    persons_service,
    files_service,
)
from zou.app.utils import events, permissions, fields

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services.exception import WrongParameterException


class ProjectsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Project)

    @jwt_required()
    def get(self):
        """
        Get projects
        ---
        tags:
          - Crud
        description: Retrieve all projects. Supports filtering via query
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
              description: Projects retrieved successfully
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
        Create project
        ---
        tags:
          - Crud
        description: Create a new project with data provided in the
          request body. JSON format is expected. Validates production_style.
          For tvshow production type, automatically creates first episode.
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
                    example: Project Name
                  production_type:
                    type: string
                    example: feature
                  production_style:
                    type: string
                    default: 2d3d
                    example: 2d3d
                  project_status_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
              description: Project created successfully
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
                        example: Project Name
                      production_type:
                        type: string
                        example: feature
                      production_style:
                        type: string
                        example: 2d3d
                      project_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      first_episode_id:
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
              description: Invalid data format or invalid production_style
        """
        return super().post()

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        else:
            return query.filter(user_service.build_related_projects_filter())

    def check_read_permissions(self, options=None):
        return True

    def check_creation_integrity(self, data):
        """
        Check if the data descriptor has a valid production_style.
        """
        if "production_style" in data:
            if data["production_style"] is None:
                data["production_style"] = "2d3d"
            if data["production_style"] not in [
                type_name for type_name, _ in PROJECT_STYLES
            ]:
                raise WrongParameterException("Invalid production_style")
        return True

    def update_data(self, data):
        data = super().update_data(data)

        if "project_status_id" not in data:
            data["project_status_id"] = (
                projects_service.get_or_create_open_status()["id"]
            )

        if "preview_background_files" in data:
            data["preview_background_files"] = [
                files_service.get_preview_background_file_raw(
                    preview_background_file_id
                )
                for preview_background_file_id in data[
                    "preview_background_files"
                ]
            ]

        if data.get("preview_background_file_id") is not None:
            if (
                "preview_background_files" not in data
                or data["preview_background_file_id"]
                not in data["preview_background_files_ids"]
            ):
                raise WrongParameterException(
                    "Invalid preview_background_file_id"
                )
        return data

    def post_creation(self, project):
        project_dict = project.serialize()
        if project.production_type == "tvshow":
            episode = shots_service.create_episode(
                project.id,
                "E01",
                created_by=persons_service.get_current_user()["id"],
            )
            project_dict["first_episode_id"] = fields.serialize_value(
                episode["id"]
            )
        user_service.clear_project_cache()
        projects_service.clear_project_cache("")
        return project_dict


class ProjectResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Project)
        self.protected_fields.append("team")

    def check_read_permissions(self, project):
        return user_service.check_project_access(project["id"])

    @jwt_required()
    def get(self, instance_id):
        """
        Get project
        ---
        tags:
          - Crud
        description: Retrieve a project by its ID and return it as a JSON
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
              description: Project retrieved successfully
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
                        example: Project Name
                      production_type:
                        type: string
                        example: feature
                      production_style:
                        type: string
                        example: 2d3d
                      project_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      project_status_name:
                        type: string
                        example: Open
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
        Update project
        ---
        tags:
          - Crud
        description: Update a project with data provided in the request
          body. JSON format is expected. Requires manager access to the
          project. Validates production_style.
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
                    example: Updated Project Name
                  production_style:
                    type: string
                    example: 2d
                  preview_background_file_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
              description: Project updated successfully
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
                        example: Updated Project Name
                      production_type:
                        type: string
                        example: feature
                      production_style:
                        type: string
                        example: 2d
                      project_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      first_episode_id:
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
              description: Invalid data format or invalid production_style
        """
        return super().put(instance_id)

    def check_update_permissions(self, project, data):
        return user_service.check_manager_project_access(project["id"])

    def pre_update(self, project_dict, data):
        if "preview_background_files" in data:
            data["preview_background_files"] = [
                files_service.get_preview_background_file_raw(
                    preview_background_file_id
                )
                for preview_background_file_id in data[
                    "preview_background_files"
                ]
            ]

        if data.get("preview_background_file_id") is not None:
            if "preview_background_files" in data:
                preview_background_files_ids = [
                    str(preview_background_file.id)
                    for preview_background_file in data[
                        "preview_background_files"
                    ]
                ]
            else:
                preview_background_files_ids = [
                    preview_background_file_id
                    for preview_background_file_id in project_dict[
                        "preview_background_files"
                    ]
                ]
            if (
                data["preview_background_file_id"]
                not in preview_background_files_ids
            ):
                raise WrongParameterException(
                    "Invalid preview_background_file_id"
                )

        return data

    def post_update(self, project_dict, data):
        if project_dict["production_type"] == "tvshow":
            episode = shots_service.get_or_create_first_episode(
                project_dict["id"],
                created_by=persons_service.get_current_user()["id"],
            )
            project_dict["first_episode_id"] = fields.serialize_value(
                episode["id"]
            )
        projects_service.clear_project_cache(project_dict["id"])
        return project_dict

    def clean_get_result(self, data):
        project_status = ProjectStatus.get(data["project_status_id"])
        data["project_status_name"] = project_status.name
        return data

    def post_delete(self, project_dict):
        projects_service.clear_project_cache(project_dict["id"])
        return project_dict

    def update_data(self, data, instance_id):
        """
        Check if the data descriptor has a valid production_style.
        """
        data = super().update_data(data, instance_id)
        if "production_style" in data:
            if data["production_style"] is None:
                data["production_style"] = "2d3d"
            if data["production_style"] not in [
                type_name for type_name, _ in PROJECT_STYLES
            ]:
                raise WrongParameterException("Invalid production_style")
        return data

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete project
        ---
        tags:
          - Crud
        description: Delete a project by its ID. Only closed projects can
          be deleted. Returns empty response on success.
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
            description: Force deletion with cascading removal
        responses:
            204:
              description: Project deleted successfully
            400:
              description: Only closed projects can be deleted or integrity error
        """
        force = self.get_force()

        project = self.get_model_or_404(instance_id)
        project_dict = project.serialize()
        if projects_service.is_open(project_dict):
            return {
                "error": True,
                "message": "Only closed projects can be deleted",
            }, 400
        else:
            self.check_delete_permissions(project_dict)
            if force:
                deletion_service.remove_project(instance_id)
            else:
                project.delete()
                events.emit("project:delete", {"project_id": project.id})
            self.post_delete(project_dict)
            return "", 204


class ProjectTaskTypeLinksResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self):
        """
        Create project task type link
        ---
        tags:
          - Crud
        description: Create a link between a project and a task type.
          Sets the priority of the task type within the project.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - project_id
                  - task_type_id
                properties:
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_type_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  priority:
                    type: integer
                    default: 1
                    example: 1
                    description: Priority of the task type in the project
        responses:
            201:
              description: Project task type link created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      project_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_type_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      priority:
                        type: integer
                        example: 1
            400:
              description: Invalid project or task type
        """
        args = self.get_args(
            [
                ("project_id", "", True),
                ("task_type_id", "", True),
                ("priority", 1, False, int),
            ]
        )

        user_service.check_manager_project_access(args["project_id"])

        task_type_link = projects_service.create_project_task_type_link(
            args["project_id"],
            args["task_type_id"],
            args["priority"],
        )
        projects_service.clear_project_cache(task_type_link["project_id"])
        return task_type_link, 201


class ProjectTaskStatusLinksResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self):
        """
        Create project task status link
        ---
        tags:
          - Crud
        description: Create a link between a project and a task status.
          Sets the priority and roles that can view it on the board.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - project_id
                  - task_status_id
                properties:
                  project_id:
                    type: string
                    format: uuid
                    example: a24a6ea4-ce75-4665-a070-57453082c25
                  task_status_id:
                    type: string
                    format: uuid
                    example: b24a6ea4-ce75-4665-a070-57453082c25
                  priority:
                    type: integer
                    default: 1
                    example: 1
                    description: Priority of the task status in the project
                  roles_for_board:
                    type: array
                    items:
                      type: string
                    example: ["admin", "manager"]
                    description: Roles allowed to see this status on the board
        responses:
            201:
              description: Project task status link created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: c24a6ea4-ce75-4665-a070-57453082c25
                      project_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      task_status_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      priority:
                        type: integer
                        example: 1
                      roles_for_board:
                        type: array
                        items:
                          type: string
                        example: ["admin", "manager"]
            400:
              description: Invalid project or task status
        """
        args = self.get_args(
            [
                ("project_id", "", True),
                ("task_status_id", "", True),
                ("priority", 1, False, int),
                (
                    "roles_for_board",
                    [],
                    False,
                    str,
                    "append",
                ),
            ]
        )

        user_service.check_manager_project_access(args["project_id"])

        task_status_link = projects_service.create_project_task_status_link(
            args["project_id"],
            args["task_status_id"],
            args["priority"],
            args["roles_for_board"],
        )
        projects_service.clear_project_cache(task_status_link["project_id"])
        return task_status_link, 201
