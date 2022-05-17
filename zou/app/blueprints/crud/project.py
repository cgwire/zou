from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse


from zou.app.mixin import ArgsMixin
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    deletion_service,
    projects_service,
    shots_service,
    user_service,
    persons_service,
    assets_service,
    tasks_service,
    status_automations_service,
)
from zou.app.utils import events, permissions, fields

from .base import BaseModelResource, BaseModelsResource


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

    def update_data(self, data):
        open_status = projects_service.get_or_create_open_status()
        if "project_status_id" not in data:
            data["project_status_id"] = open_status["id"]
        if "team" in data:
            data["team"] = [
                persons_service.get_person_raw(person_id)
                for person_id in data["team"]
            ]
        if "asset_types" in data:
            data["asset_types"] = [
                assets_service.get_asset_type_raw(asset_type_id)
                for asset_type_id in data["asset_types"]
            ]
        if "task_statuses" in data:
            data["task_statuses"] = [
                tasks_service.get_task_status_raw(task_status_id)
                for task_status_id in data["task_statuses"]
            ]
        if "task_types" in data:
            data["task_types"] = [
                tasks_service.get_task_type_raw(task_type_id)
                for task_type_id in data["task_types"]
            ]
        if "status_automations" in data:
            data["status_automations"] = [
                status_automations_service.get_status_automation_raw(
                    task_type_id
                )
                for task_type_id in data["status_automations"]
            ]
        return data

    def post_creation(self, project):
        project_dict = project.serialize()
        if project.production_type == "tvshow":
            episode = shots_service.create_episode(project.id, "E01")
            project_dict["first_episode_id"] = fields.serialize_value(
                episode["id"]
            )
        user_service.clear_project_cache()
        projects_service.clear_project_cache("")
        return project_dict


class ProjectResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Project)
        self.protected_fields.append("team")

    def check_read_permissions(self, project):
        user_service.check_project_access(project["id"])

    def pre_update(self, project_dict, data):
        if "team" in data:
            data["team"] = [
                persons_service.get_person_raw(person_id)
                for person_id in data["team"]
            ]
        if "asset_types" in data:
            data["asset_types"] = [
                assets_service.get_asset_type_raw(asset_type_id)
                for asset_type_id in data["asset_types"]
            ]
        if "task_statuses" in data:
            data["task_statuses"] = [
                tasks_service.get_task_status_raw(task_status_id)
                for task_status_id in data["task_statuses"]
            ]
        if "task_types" in data:
            data["task_types"] = [
                tasks_service.get_task_type_raw(task_type_id)
                for task_type_id in data["task_types"]
            ]
        if "status_automations" in data:
            data["status_automations"] = [
                status_automations_service.get_status_automation_raw(
                    task_type_id
                )
                for task_type_id in data["status_automations"]
            ]
        return data

    def post_update(self, project_dict):
        if project_dict["production_type"] == "tvshow":
            episode = shots_service.get_or_create_first_episode(
                project_dict["id"]
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

    @jwt_required
    def delete(self, instance_id):
        parser = reqparse.RequestParser()
        parser.add_argument("force", default=False, type=bool)
        args = parser.parse_args()

        project = self.get_model_or_404(instance_id)
        project_dict = project.serialize()
        if projects_service.is_open(project_dict):
            return {
                "error": True,
                "message": "Only closed projects can be deleted",
            }, 400
        else:
            self.check_delete_permissions(project_dict)
            if args["force"] is True:
                deletion_service.remove_project(instance_id)
            else:
                project.delete()
                events.emit("project:delete", {"project_id": project.id})
            self.post_delete(project_dict)
            return "", 204


class ProjectTaskTypeLinksResource(Resource, ArgsMixin):
    @jwt_required
    def post(self):
        data = self.get_args(
            [
                ("project_id", "", True),
                ("task_type_id", "", True),
                ("priority", 1, False, None, int),
            ]
        )
        task_type_link = projects_service.create_project_task_type_link(
            data["project_id"], data["task_type_id"], data["priority"]
        )
        projects_service.clear_project_cache(task_type_link["project_id"])
        return task_type_link, 201
