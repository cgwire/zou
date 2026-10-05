from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.file_status import FileStatus
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class FileStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, FileStatus)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/FileStatusesResource_get.yml")
    def get(self):
        """
        Get file statuses
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/FileStatusesResource_post.yml")
    def post(self):
        """
        Create file status
        """
        return super().post()


class FileStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, FileStatus)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/FileStatusResource_get.yml")
    def get(self, instance_id):
        """
        Get file status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/FileStatusResource_put.yml")
    def put(self, instance_id):
        """
        Update file status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/FileStatusResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete file status
        """
        return super().delete(instance_id)
