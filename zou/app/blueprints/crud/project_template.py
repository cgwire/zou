from flask import request
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
)
from zou.app.exceptions import (
    ProjectTemplateNotFoundException,
    WrongParameterException,
)
from zou.app.models.project_template import ProjectTemplate
from zou.app.services import project_templates_service
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/project_template.yml")


class ProjectTemplatesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProjectTemplate)

    def get_relations_eager_load(self):
        return [
            ProjectTemplate.asset_types,
            ProjectTemplate.task_statuses,
            ProjectTemplate.task_types,
            ProjectTemplate.status_automations,
            ProjectTemplate.preview_background_files,
        ]

    def check_read_permissions(self, options=None):
        return permissions.check_manager_permissions()

    def check_create_permissions(self, data):
        return permissions.check_admin_permissions()

    @jwt_required()
    @swag_from(SPECS["ProjectTemplatesResource_get"])
    def get(self):
        """
        Get project templates
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ProjectTemplatesResource_post"])
    def post(self):
        """
        Create project template
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
    @swag_from(SPECS["ProjectTemplateResource_get"])
    def get(self, instance_id):
        """
        Get project template
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ProjectTemplateResource_put"])
    def put(self, instance_id):
        """
        Update project template
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
    @swag_from(SPECS["ProjectTemplateResource_delete"])
    def delete(self, instance_id):
        """
        Delete project template
        """
        permissions.check_admin_permissions()
        try:
            project_templates_service.delete_project_template(instance_id)
        except ProjectTemplateNotFoundException:
            return {"message": "Project template not found"}, 404
        return "", 204
