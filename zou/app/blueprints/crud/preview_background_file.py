from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.exceptions import WrongParameterException
from zou.app.services import files_service, deletion_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class PreviewBackgroundFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFilesResource_get.yml")
    def get(self):
        """
        Get preview background files
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFilesResource_post.yml")
    def post(self):
        """
        Create preview background file
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        name = data.get("name", None)
        preview_background_file = PreviewBackgroundFile.get_by(name=name)
        if preview_background_file is not None:
            raise WrongParameterException(
                "A preview background file with similar name already exists"
            )
        return data

    def post_creation(self, instance):
        if instance.is_default:
            files_service.reset_default_preview_background_files(instance.id)
        files_service.clear_preview_background_file_cache(str(instance.id))
        return instance.serialize(relations=True)


class PreviewBackgroundFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFileResource_get.yml")
    def get(self, instance_id):
        """
        Get preview background file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFileResource_put.yml")
    def put(self, instance_id):
        """
        Update preview background file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFileResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete preview background file
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        name = data.get("name", None)
        if name is not None:
            preview_background_file = PreviewBackgroundFile.get_by(name=name)
            if preview_background_file is not None and instance_id != str(
                preview_background_file.id
            ):
                raise WrongParameterException(
                    "A preview background file with similar name already exists"
                )
        return data

    def post_update(self, instance_dict, data):
        if instance_dict["is_default"]:
            files_service.reset_default_preview_background_files(
                instance_dict["id"]
            )
        files_service.clear_preview_background_file_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        deletion_service.clear_preview_background_files(instance_dict["id"])
        files_service.clear_preview_background_file_cache(instance_dict["id"])
        return instance_dict
