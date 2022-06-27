from zou.app.models.software import Software
from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_softwares


@name_space_softwares.route('/')
class SoftwaresResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Software)

    def check_read_permissions(self):
        return True


@name_space_softwares.route('/<instance_id>')
class SoftwareResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Software)

    def check_read_permissions(self, instance):
        return True
