from flask import request
from flask_jwt_extended import jwt_required
from flask_restful import Resource

from zou.app.mixin import ArgsMixin
from zou.app.services import project_templates_service
from zou.app.services.exception import (
    ProjectNotFoundException,
    ProjectTemplateNotFoundException,
    WrongParameterException,
)
from zou.app.utils import permissions


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


class ProjectTemplateTaskTypesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List task types attached to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_manager_permissions()
        try:
            return project_templates_service.get_template_task_types(
                template_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
        """
        Attach a task type to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args(
            [
                ("task_type_id", "", True),
                ("priority", None, False, int),
            ]
        )
        try:
            link = project_templates_service.add_task_type_to_template(
                template_id,
                args["task_type_id"],
                args["priority"],
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return link, 201


class ProjectTemplateTaskTypeResource(Resource):
    @jwt_required()
    def delete(self, template_id, task_type_id):
        """
        Detach a task type from a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_task_type_from_template(
                template_id, task_type_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateTaskStatusesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List task statuses attached to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_manager_permissions()
        try:
            return project_templates_service.get_template_task_statuses(
                template_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
        """
        Attach a task status to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args(
            [
                ("task_status_id", "", True),
                ("priority", None, False, int),
                ("roles_for_board", [], False, str, "append"),
            ]
        )
        try:
            link = project_templates_service.add_task_status_to_template(
                template_id,
                args["task_status_id"],
                args["priority"],
                args["roles_for_board"] or None,
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return link, 201


class ProjectTemplateTaskStatusResource(Resource):
    @jwt_required()
    def delete(self, template_id, task_status_id):
        """
        Detach a task status from a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_task_status_from_template(
                template_id, task_status_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateAssetTypesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List asset types attached to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_manager_permissions()
        try:
            return project_templates_service.get_template_asset_types(
                template_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
        """
        Attach an asset type to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args([("asset_type_id", "", True)])
        try:
            entry = project_templates_service.add_asset_type_to_template(
                template_id, args["asset_type_id"]
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateAssetTypeResource(Resource):
    @jwt_required()
    def delete(self, template_id, asset_type_id):
        """
        Detach an asset type from a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_asset_type_from_template(
                template_id, asset_type_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateStatusAutomationsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List status automations attached to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_manager_permissions()
        try:
            return (
                project_templates_service.get_template_status_automations(
                    template_id
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
        """
        Attach a status automation to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args([("status_automation_id", "", True)])
        try:
            entry = (
                project_templates_service.add_status_automation_to_template(
                    template_id, args["status_automation_id"]
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateStatusAutomationResource(Resource):
    @jwt_required()
    def delete(self, template_id, status_automation_id):
        """
        Detach a status automation from a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_status_automation_from_template(
                template_id, status_automation_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateBackgroundsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List preview background files attached to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_manager_permissions()
        try:
            return (
                project_templates_service.get_template_preview_background_files(
                    template_id
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
        """
        Attach a preview background file to a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args([("preview_background_file_id", "", True)])
        try:
            entry = (
                project_templates_service.add_preview_background_file_to_template(
                    template_id, args["preview_background_file_id"]
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateBackgroundResource(Resource):
    @jwt_required()
    def delete(self, template_id, preview_background_file_id):
        """
        Detach a preview background file from a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_preview_background_file_from_template(
                template_id, preview_background_file_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateDefaultBackgroundResource(Resource):
    @jwt_required()
    def put(self, template_id):
        """
        Set the default preview background file for a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        data = request.json or {}
        background_id = data.get("default_preview_background_file_id")
        try:
            template = (
                project_templates_service.set_template_default_preview_background_file(
                    template_id, background_id
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 200


class ProjectTemplateMetadataDescriptorsResource(Resource):
    @jwt_required()
    def put(self, template_id):
        """
        Replace the JSONB metadata descriptors snapshot on a project
        template. Admin only.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        data = request.json or {}
        descriptors = data.get("metadata_descriptors")
        if descriptors is None and isinstance(data, list):
            descriptors = data
        try:
            template = (
                project_templates_service.set_template_metadata_descriptors(
                    template_id, descriptors
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 200


# ---------------------------------------------------------------------------
# Snapshot / apply
# ---------------------------------------------------------------------------


class ProjectTemplateFromProjectResource(Resource, ArgsMixin):
    @jwt_required()
    def post(self, project_id):
        """
        Create a new project template from an existing project's
        configuration. Admin only.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        args = self.get_args(
            [
                ("name", "", True),
                ("description", None, False),
            ]
        )
        try:
            template = (
                project_templates_service.create_template_from_project(
                    project_id,
                    args["name"],
                    description=args["description"],
                )
            )
        except ProjectNotFoundException:
            return {"message": "Project not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 201


class ApplyProjectTemplateResource(Resource):
    @jwt_required()
    def post(self, project_id, template_id):
        """
        Apply a project template to an existing project. Admin only.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        try:
            project = project_templates_service.apply_template_to_project(
                project_id, template_id
            )
        except ProjectNotFoundException:
            return {"message": "Project not found"}, 404
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return project, 200
