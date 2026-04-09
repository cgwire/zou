from flask import request
from flask_jwt_extended import jwt_required
from flask_restful import Resource

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
)
from zou.app.mixin import ArgsMixin
from zou.app.models.project_template import ProjectTemplate
from zou.app.services import project_templates_service, projects_service
from zou.app.services.exception import (
    ProjectNotFoundException,
    ProjectTemplateNotFoundException,
    WrongParameterException,
)
from zou.app.utils import permissions


class ProjectTemplatesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProjectTemplate)

    def check_read_permissions(self, options=None):
        return permissions.check_manager_permissions()

    def check_create_permissions(self, data):
        return permissions.check_admin_permissions()

    @jwt_required()
    def get(self):
        """
        Get project templates
        ---
        tags:
          - Crud
        description: Retrieve all project templates. Manager+ access.
        responses:
            200:
              description: Project templates retrieved successfully
        """
        return super().get()

    @jwt_required()
    def post(self):
        """
        Create project template
        ---
        tags:
          - Crud
        description: Create a new empty project template. Admin only.
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
                  description:
                    type: string
                  fps:
                    type: string
                  ratio:
                    type: string
                  resolution:
                    type: string
                  production_type:
                    type: string
                  production_style:
                    type: string
        responses:
            201:
              description: Project template created successfully
            400:
              description: Invalid data or duplicate name
        """
        data = request.json or {}
        self.check_create_permissions(data)
        try:
            template = project_templates_service.create_project_template(
                **data
            )
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 201


class ProjectTemplateResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProjectTemplate)

    def check_read_permissions(self, instance):
        return permissions.check_manager_permissions()

    def check_update_permissions(self, instance, data):
        return permissions.check_admin_permissions()

    def check_delete_permissions(self, instance):
        return permissions.check_admin_permissions()

    @jwt_required()
    def get(self, instance_id):
        """
        Get project template
        ---
        tags:
          - Crud
        description: Retrieve a project template by its ID. Manager+ access.
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update project template
        ---
        tags:
          - Crud
        description: Update a project template. Admin only.
        """
        data = request.json or {}
        self.check_update_permissions(None, data)
        try:
            template = project_templates_service.update_project_template(
                instance_id, data
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        except WrongParameterException as exception:
            return {"message": str(exception)}, 400
        return template, 200

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete project template
        ---
        tags:
          - Crud
        description: Delete a project template. Admin only.
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.delete_project_template(instance_id)
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


# ---------------------------------------------------------------------------
# Link management
# ---------------------------------------------------------------------------


class ProjectTemplateTaskTypesResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self, template_id):
        """
        List task types attached to a project template.
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
        permissions.check_manager_permissions()
        try:
            return project_templates_service.get_template_task_statuses(
                template_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
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
        permissions.check_manager_permissions()
        try:
            return project_templates_service.get_template_asset_types(
                template_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404

    @jwt_required()
    def post(self, template_id):
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
        permissions.check_admin_permissions()
        try:
            project_templates_service.remove_status_automation_from_template(
                template_id, status_automation_id
            )
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204


class ProjectTemplateMetadataDescriptorsResource(Resource):
    @jwt_required()
    def put(self, template_id):
        """
        Replace the JSONB metadata descriptors snapshot on a project
        template. Admin only.
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
