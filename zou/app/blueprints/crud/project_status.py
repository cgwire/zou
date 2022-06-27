from zou.app.models.project_status import ProjectStatus
from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_project_status


@name_space_project_status.route('/')
class ProjectStatussResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProjectStatus)

    def check_read_permissions(self):
        return True


@name_space_project_status.route('/<instance_id>')
class ProjectStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProjectStatus)

    def check_read_permissions(self, instance):
        return True
