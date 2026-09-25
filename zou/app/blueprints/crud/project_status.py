from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.project_status import ProjectStatus
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class ProjectStatussResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProjectStatus)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/ProjectStatussResource_get.yml")
    def get(self):
        """
        Get project statuses
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ProjectStatussResource_post.yml")
    def post(self):
        """
        Create project status
        """
        return super().post()


class ProjectStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProjectStatus)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/ProjectStatusResource_get.yml")
    def get(self, instance_id):
        """
        Get project status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ProjectStatusResource_put.yml")
    def put(self, instance_id):
        """
        Update project status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/ProjectStatusResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete project status
        """
        return super().delete(instance_id)
