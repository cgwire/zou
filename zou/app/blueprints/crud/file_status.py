from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.file_status import FileStatus
from zou.app.services import files_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/file_status.yml")


class FileStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, FileStatus)

    def post_creation(self, instance):
        files_service.clear_file_status_cache()
        return super().post_creation(instance)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["FileStatusesResource_get"])
    def get(self):
        """
        Get file statuses
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["FileStatusesResource_post"])
    def post(self):
        """
        Create file status
        """
        return super().post()


class FileStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, FileStatus)

    def post_update(self, instance_dict, data):
        files_service.clear_file_status_cache()
        return instance_dict

    def post_delete(self, instance_dict):
        files_service.clear_file_status_cache()
        return instance_dict

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from(SPECS["FileStatusResource_get"])
    def get(self, instance_id):
        """
        Get file status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["FileStatusResource_put"])
    def put(self, instance_id):
        """
        Update file status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["FileStatusResource_delete"])
    def delete(self, instance_id):
        """
        Delete file status
        """
        return super().delete(instance_id)
