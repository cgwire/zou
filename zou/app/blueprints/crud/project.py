from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.mixin import ArgsMixin
from zou.app.models.project import PROJECT_STYLES, Project
from zou.app.services import (
    cascade_deletion_service,
    files_service,
    metadata_descriptors_service,
    permissions_service,
    persons_service,
    project_templates_service,
    projects_service,
    shots_service,
    user_service,
)
from zou.app.utils import events, fields, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/project.yml")


class ProjectsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Project)
        # Keep the template state between update_data() and post_creation().
        # Thus post_creation() knows what to apply after the project insert,
        # and which fields the caller gave. These fields override the template
        # values.
        self._template_id_to_apply = None
        self._template_overrides = {}

    def all_entries(self, query=None, relations=False):
        # A project in the list is the same as the project read by its ID, with
        # the extra data, for all values of relations. gazu reads both and
        # expects one shape.
        if query is None:
            query = self.model.query
        return user_service.serialize_projects(query)

    @jwt_required()
    @swag_from(SPECS["ProjectsResource_get"])
    def get(self):
        """
        Get projects
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ProjectsResource_post"])
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
        Make sure that the project has a valid production_style, resolution
        and movie bitrates. A null production_style becomes 2d3d.
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

        # Remove project_template_id from the payload before the Project model
        # gets it. Keep the names of the fields that the caller gave, so that
        # apply_template_to_project() can ignore them (explicit > template).
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
        # Each metadata column for all projects is one Project descriptor row
        # for each project. Copy them to the new project. Thus users can edit
        # its cells immediately, and the client does not send one create
        # request for each descriptor.
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
        # With its relations, the project is the same as in the list of open
        # projects, with the extra data. A closed project is not in that list,
        # thus the client reads it by its ID. It also gets its metadata
        # descriptors, task type priorities, and task status links.
        if not relations:
            return super().get_serialized_instance(instance_id, relations)
        project = self.get_model_or_404(instance_id)
        # The serialization of the read occurs before check_read_permissions.
        # The descriptors depend on a role that can be different for each
        # project. Thus do the access check first, because it finds that role.
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
    @swag_from(SPECS["ProjectResource_get"])
    def get(self, instance_id):
        """
        Get project
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ProjectResource_put"])
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

        for field in (
            "preview_background_file_id",
            "default_preview_background_file_id",
        ):
            if data.get(field) is None:
                continue
            if "preview_background_files" in data:
                preview_background_files_ids = [
                    str(preview_background_file.id)
                    for preview_background_file in data[
                        "preview_background_files"
                    ]
                ]
            else:
                preview_background_files_ids = [
                    str(preview_background_file.id)
                    for preview_background_file in projects_service.get_project_raw(
                        project_dict["id"]
                    ).preview_background_files
                ]
            if data[field] not in preview_background_files_ids:
                raise WrongParameterException(f"Invalid {field}")

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
        project_status = projects_service.get_project_status_raw(
            data["project_status_id"]
        )
        data["project_status_name"] = project_status.name
        return data

    def post_delete(self, project_dict):
        projects_service.clear_project_cache(project_dict["id"])
        return project_dict

    def update_data(self, data, instance_id):
        """
        Make sure that the project has a valid production_style. A null
        production_style becomes 2d3d.
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
    @swag_from(SPECS["ProjectResource_delete"])
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
            # Without force, the delete fails on the foreign keys of the tasks
            # and entities. Refuse it before the removal of data.
            if not force and projects_service.has_tasks_or_entities(
                instance_id
            ):
                return {
                    "error": True,
                    "message": "The project has tasks or entities, use the "
                    "force parameter to delete them with the project.",
                }, 400
            if force:
                cascade_deletion_service.remove_project(instance_id)
            else:
                cascade_deletion_service.remove_preview_account(instance_id)
                project.delete()
                events.emit("project:delete", {"project_id": project.id})
            self.post_delete(project_dict)
            return "", 204


class ProjectTaskTypeLinksResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from(SPECS["ProjectTaskTypeLinksResource_post"])
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
    @swag_from(SPECS["ProjectTaskStatusLinksResource_post"])
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
    @swag_from(SPECS["ProjectTaskTypeLinksReorderResource_post"])
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
    @swag_from(SPECS["ProjectTaskStatusLinksReorderResource_post"])
    def post(self, project_id):
        """
        Reorder project task status links
        """
        permissions_service.check_manager_project_access(project_id)
        task_status_ids = _validate_id_list_body("task_status_ids")
        return projects_service.set_project_task_status_link_priorities(
            project_id, task_status_ids
        )
