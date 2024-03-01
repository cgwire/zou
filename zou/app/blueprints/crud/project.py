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

from zou.app.services.exception import ArgumentsException


class ProjectsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Project)

    def add_project_permission_filter(self, query):
        if permissions.has_admin_permissions():
            return query
        else:
            return query.filter(user_service.build_related_projects_filter())

    def check_read_permissions(self):
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
                raise ArgumentsException("Invalid production_style")
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
                raise ArgumentsException("Invalid preview_background_file_id")
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
                raise ArgumentsException("Invalid preview_background_file_id")

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
                raise ArgumentsException("Invalid production_style")
        return data

    @jwt_required()
    def delete(self, instance_id):
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
        args = self.get_args(
            [
                ("project_id", "", True),
                ("task_type_id", "", True),
                ("priority", 1, False, int),
            ]
        )

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

        task_status_link = projects_service.create_project_task_status_link(
            args["project_id"],
            args["task_status_id"],
            args["priority"],
            args["roles_for_board"],
        )
        projects_service.clear_project_cache(task_status_link["project_id"])
        return task_status_link, 201
