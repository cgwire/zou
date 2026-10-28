from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.services import deletion_service, files_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/preview_background_file.yml")


class PreviewBackgroundFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["PreviewBackgroundFilesResource_get"])
    def get(self):
        """
        Get preview background files
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["PreviewBackgroundFilesResource_post"])
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
    @swag_from(SPECS["PreviewBackgroundFileResource_get"])
    def get(self, instance_id):
        """
        Get preview background file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["PreviewBackgroundFileResource_put"])
    def put(self, instance_id):
        """
        Update preview background file
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["PreviewBackgroundFileResource_delete"])
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
