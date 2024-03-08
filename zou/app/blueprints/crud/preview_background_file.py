from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.services.exception import ArgumentsException
from zou.app.services import files_service

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class PreviewBackgroundFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self):
        return True

    def update_data(self, data):
        data = super().update_data(data)
        name = data.get("name", None)
        preview_background_file = PreviewBackgroundFile.get_by(name=name)
        if preview_background_file is not None:
            raise ArgumentsException(
                "A preview background file with similar name already exists"
            )
        return data

    def post_creation(self, instance):
        if instance.is_default:
            files_service.reset_default_preview_background_files(instance.id)
        files_service.clear_preview_background_file_cache(str(instance.id))
        return instance.serialize()


class PreviewBackgroundFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewBackgroundFile)

    def check_read_permissions(self, instance):
        return True

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        name = data.get("name", None)
        if name is not None:
            preview_background_file = PreviewBackgroundFile.get_by(name=name)
            if preview_background_file is not None and instance_id != str(
                preview_background_file.id
            ):
                raise ArgumentsException(
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
        # stop removing files for now
        # deletion_service.clear_preview_background_files(instance_dict["id"])
        files_service.clear_preview_background_file_cache(instance_dict["id"])
        return instance_dict
