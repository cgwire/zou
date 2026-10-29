from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.project_status import ProjectStatus
from zou.app.services import projects_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/project_status.yml")


class ProjectStatussResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProjectStatus)

    def post_creation(self, instance):
        projects_service.clear_project_status_cache()
        return super().post_creation(instance)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["ProjectStatussResource_get"])
    def get(self):
        """
        Get project statuses
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ProjectStatussResource_post"])
    def post(self):
        """
        Create project status
        """
        return super().post()


class ProjectStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProjectStatus)

    def post_update(self, instance_dict, data):
        projects_service.clear_project_status_cache()
        return instance_dict

    def post_delete(self, instance_dict):
        projects_service.clear_project_status_cache()
        return instance_dict

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from(SPECS["ProjectStatusResource_get"])
    def get(self, instance_id):
        """
        Get project status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ProjectStatusResource_put"])
    def put(self, instance_id):
        """
        Update project status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["ProjectStatusResource_delete"])
    def delete(self, instance_id):
        """
        Delete project status
        """
        return super().delete(instance_id)
