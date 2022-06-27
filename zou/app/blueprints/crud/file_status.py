from zou.app.models.file_status import FileStatus
from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_file_status


@name_space_file_status.route('/')
class FileStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, FileStatus)

    def check_read_permissions(self):
        return True


@name_space_file_status.route('/<instance_id>')
class FileStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, FileStatus)

    def check_read_permissions(self, instance):
        return True
