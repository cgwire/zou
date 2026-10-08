from flasgger import swag_from
from flask import request
from flask_jwt_extended import jwt_required

from flask.views import MethodView


from zou.app.mixin import ArgsMixin
from zou.app.models.project import Project, PROJECT_STYLES
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    deletion_service,
    project_templates_service,
    projects_service,
    shots_service,
    permissions_service,
    user_service,
    persons_service,
    files_service,
    metadata_descriptors_service,
)
from zou.app.utils import events, permissions, fields

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.exceptions import WrongParameterException


class ProjectsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Project)
        # Stash template state between update_data() and post_creation()
        # so we know what to apply after the project is inserted, and which
        # explicit fields the caller passed (those override template values).
        self._template_id_to_apply = None
        self._template_overrides = {}

    def get_relations_eager_load(self):
        return [
            Project.asset_types,
            Project.task_statuses,
            Project.task_types,
            Project.status_automations,
            Project.preview_background_files,
        ]

    @jwt_required()
    @swag_from("openapi/ProjectsResource_get.yml")
    def get(self):
        """
        Get projects
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ProjectsResource_post.yml")
    def post(self):
        """
        Create project
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
        Check if the data descriptor has a valid production_style and
        resolution.
        """
        if "production_style" in data:
            if data["production_style"] is None:
                data["production_style"] = "2d3d"
            if data["production_style"] not in [
                type_name for type_name, _ in PROJECT_STYLES
            ]:
                raise WrongParameterException("Invalid production_style")
        if "resolution" in data:
            projects_service.validate_resolution(data["resolution"])
        projects_service.validate_movie_bitrates(data)
        return True

    def update_data(self, data):
        data = super().update_data(data)

        # Pull project_template_id out of the payload before it reaches the
        # Project model, but remember which fields the caller provided so
        # apply_template_to_project() can skip them (explicit > template).
        self._template_id_to_apply = data.pop("project_template_id", None)
        if self._template_id_to_apply:
            self._template_overrides = {
                key: value for key, value in data.items() if value is not None
            }

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

        if data.get("default_preview_background_file_id") is not None:
            preview_background_files_ids = [
                str(preview_background_file.id)
                for preview_background_file in data.get(
                    "preview_background_files", []
                )
            ]
            if (
                data["default_preview_background_file_id"]
                not in preview_background_files_ids
            ):
                raise WrongParameterException(
                    "Invalid default_preview_background_file_id"
                )
        return data

    def post_creation(self, project):
        project_dict = project.serialize(relations=True)
        if self._template_id_to_apply is not None:
            project_templates_service.apply_template_to_project(
                str(project.id),
                self._template_id_to_apply,
                override_settings=self._template_overrides,
            )
            project_dict = project.serialize(relations=True)
        if project.production_type == "tvshow":
            episode = shots_service.create_episode(
                project.id,
                "E01",
                created_by=persons_service.get_current_user()["id"],
            )
            project_dict["first_episode_id"] = fields.serialize_value(
                episode["id"]
            )
        # The all-projects metadata columns are one Project descriptor row
        # per project: copy them onto the new project so its cells are
        # editable right away, instead of one create request per descriptor
        # from the client.
        metadata_descriptors_service.copy_project_metadata_descriptors(
            str(project.id)
        )
        user_service.clear_open_projects_cache()
        projects_service.clear_project_cache("")
        return project_dict


class ProjectResource(BaseModelResource, ArgsMixin):
    def __init__(self):
        BaseModelResource.__init__(self, Project)
        self.protected_fields.append("team")

    def check_read_permissions(self, project):
        return permissions_service.check_project_access(project["id"])

    def get_serialized_instance(self, instance_id, relations=True):
        # With its relations, the project is the one the open projects
        # listing serves, extra data included: a closed project, read by
        # its id since it is out of that listing, was missing its metadata
        # descriptors, task type priorities, and task status links.
        if not relations:
            return super().get_serialized_instance(instance_id, relations)
        project = self.get_model_or_404(instance_id)
        # The read is serialized before check_read_permissions runs, and the
        # descriptors are narrowed on a role that can be set per project:
        # the access check comes first, it resolves that role.
        permissions_service.check_project_access(str(project.id))
        for_client, vendor_departments = (
            permissions_service.get_descriptor_visibility(
                permissions.get_effective_role()
            )
        )
        return projects_service.get_project_with_extra_data(
            project, for_client, vendor_departments
        )

    @jwt_required()
    @swag_from("openapi/ProjectResource_get.yml")
    def get(self, instance_id):
        """
        Get project
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ProjectResource_put.yml")
    def put(self, instance_id):
        """
        Update project
        """
        return super().put(instance_id)

    def check_update_permissions(self, project, data):
        return permissions_service.check_manager_project_access(project["id"])

    def pre_update(self, project_dict, data):
        if "resolution" in data:
            projects_service.validate_resolution(data["resolution"])
        projects_service.validate_movie_bitrates(data, current=project_dict)

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
    @swag_from("openapi/ProjectResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete project
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


class ProjectTaskTypeLinksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectTaskTypeLinksResource_post.yml")
    def post(self):
        """
        Create project task type link
        """
        args = self.get_args(
            [
                ("project_id", "", True),
                ("task_type_id", "", True),
                ("priority", 1, False, int),
            ]
        )

        permissions_service.check_manager_project_access(args["project_id"])

        task_type_link = projects_service.create_project_task_type_link(
            args["project_id"],
            args["task_type_id"],
            args["priority"],
        )
        return task_type_link, 201


class ProjectTaskStatusLinksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/ProjectTaskStatusLinksResource_post.yml")
    def post(self):
        """
        Create project task status link
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

        permissions_service.check_manager_project_access(args["project_id"])

        task_status_link = projects_service.create_project_task_status_link(
            args["project_id"],
            args["task_status_id"],
            args["priority"],
            args["roles_for_board"],
        )
        return task_status_link, 201


def _validate_id_list_body(key):
    body = request.json
    if not isinstance(body, dict) or not isinstance(body.get(key), list):
        raise WrongParameterException(
            f"Request body must be a JSON object with a '{key}' list."
        )
    return body[key]


class ProjectTaskTypeLinksReorderResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectTaskTypeLinksReorderResource_post.yml")
    def post(self, project_id):
        """
        Reorder project task type links
        """
        permissions_service.check_manager_project_access(project_id)
        task_type_ids = _validate_id_list_body("task_type_ids")
        return projects_service.set_project_task_type_link_priorities(
            project_id, task_type_ids
        )


class ProjectTaskStatusLinksReorderResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ProjectTaskStatusLinksReorderResource_post.yml")
    def post(self, project_id):
        """
        Reorder project task status links
        """
        permissions_service.check_manager_project_access(project_id)
        task_status_ids = _validate_id_list_body("task_status_ids")
        return projects_service.set_project_task_status_link_priorities(
            project_id, task_status_ids
        )
