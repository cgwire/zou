from flask import request
from flask_jwt_extended import jwt_required
from flask.views import MethodView

from zou.app.services import project_templates_service
from zou.app.services.exception import (
    ProjectNotFoundException,
    ProjectTemplateNotFoundException,
    WrongParameterException,
)
from zou.app.utils import permissions, validation
from zou.app.blueprints.project_templates.schemas import (
    SetDefaultBackgroundSchema,
    AddAssetTypeSchema,
    AddBackgroundSchema,
    AddStatusAutomationSchema,
    AddTaskStatusSchema,
    AddTaskTypeSchema,
    CreateTemplateFromProjectSchema,
    SetMetadataDescriptorsSchema,
)

# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


class ProjectTemplateTaskTypesResource(MethodView):
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
        data = validation.validate_request_body(AddTaskTypeSchema)
        try:
            link = project_templates_service.add_task_type_to_template(
                template_id,
                data.task_type_id,
                data.priority,
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return link, 201


class ProjectTemplateTaskTypeResource(MethodView):
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


class ProjectTemplateTaskStatusesResource(MethodView):
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
        data = validation.validate_request_body(AddTaskStatusSchema)
        try:
            link = project_templates_service.add_task_status_to_template(
                template_id,
                data.task_status_id,
                data.priority,
                data.roles_for_board or None,
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return link, 201


class ProjectTemplateTaskStatusResource(MethodView):
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


class ProjectTemplateAssetTypesResource(MethodView):
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
        data = validation.validate_request_body(AddAssetTypeSchema)
        try:
            entry = project_templates_service.add_asset_type_to_template(
                template_id, data.asset_type_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateAssetTypeResource(MethodView):
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


class ProjectTemplateStatusAutomationsResource(MethodView):
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
            return project_templates_service.get_template_status_automations(
                template_id
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
        data = validation.validate_request_body(AddStatusAutomationSchema)
        try:
            entry = (
                project_templates_service.add_status_automation_to_template(
                    template_id, data.status_automation_id
                )
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateStatusAutomationResource(MethodView):
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


class ProjectTemplateBackgroundsResource(MethodView):
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
            return project_templates_service.get_template_preview_background_files(
                template_id
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
        data = validation.validate_request_body(AddBackgroundSchema)
        try:
            entry = project_templates_service.add_preview_background_file_to_template(
                template_id, data.preview_background_file_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return entry, 201


class ProjectTemplateBackgroundResource(MethodView):
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


class ProjectTemplateDefaultBackgroundResource(MethodView):
    @jwt_required()
    def put(self, template_id):
        """
        Set the default preview background file for a project template.
        ---
        tags:
          - Project Templates
        """
        permissions.check_admin_permissions()
        data = validation.validate_request_body(SetDefaultBackgroundSchema)
        try:
            template = project_templates_service.set_template_default_preview_background_file(
                template_id, data.default_preview_background_file_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 200


class ProjectTemplateMetadataDescriptorsResource(MethodView):
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
        body = request.get_json(silent=True)
        if isinstance(body, list):
            # Legacy shape: the descriptors sent as a bare JSON array.
            descriptors = body
        else:
            descriptors = validation.validate_request_body(
                SetMetadataDescriptorsSchema
            ).metadata_descriptors
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


class ProjectTemplateFromProjectResource(MethodView):
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
        data = validation.validate_request_body(
            CreateTemplateFromProjectSchema
        )
        try:
            template = project_templates_service.create_template_from_project(
                project_id,
                data.name,
                description=data.description,
            )
        except ProjectNotFoundException:
            return {"message": "Project not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 201


class ApplyProjectTemplateResource(MethodView):
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


class ProjectTemplateTaskTypesReorderResource(MethodView):
    @jwt_required()
    def post(self, template_id):
        """
        Reorder template task types
        ---
        tags:
          - Project templates
        description: Set the priority of the template's task type links from
          the given ordered id list in a single request, replacing one link
          request per task type.
        parameters:
          - in: path
            name: template_id
            required: true
            schema:
              type: string
              format: uuid
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_type_ids
                properties:
                  task_type_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
        responses:
            200:
              description: Updated task type links
        """
        permissions.check_admin_permissions()
        body = request.json
        if not isinstance(body, dict) or not isinstance(
            body.get("task_type_ids"), list
        ):
            raise WrongParameterException(
                "Request body must be a JSON object with a "
                "'task_type_ids' list."
            )
        return project_templates_service.set_template_task_type_priorities(
            template_id, body["task_type_ids"]
        )


class ProjectTemplateTaskStatusesReorderResource(MethodView):
    @jwt_required()
    def post(self, template_id):
        """
        Reorder template task statuses
        ---
        tags:
          - Project templates
        description: Set the priority of the template's task status links from
          the given ordered id list in a single request, preserving each
          link's board roles and replacing one link request per status.
        parameters:
          - in: path
            name: template_id
            required: true
            schema:
              type: string
              format: uuid
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_status_ids
                properties:
                  task_status_ids:
                    type: array
                    items:
                      type: string
                      format: uuid
        responses:
            200:
              description: Updated task status links
        """
        permissions.check_admin_permissions()
        body = request.json
        if not isinstance(body, dict) or not isinstance(
            body.get("task_status_ids"), list
        ):
            raise WrongParameterException(
                "Request body must be a JSON object with a "
                "'task_status_ids' list."
            )
        return project_templates_service.set_template_task_status_priorities(
            template_id, body["task_status_ids"]
        )
