from flask import request
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
)
from zou.app.models.project_template import ProjectTemplate
from zou.app.services import project_templates_service
from zou.app.services.exception import (
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
