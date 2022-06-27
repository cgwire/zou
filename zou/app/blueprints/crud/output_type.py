from zou.app.models.output_type import OutputType
from .base import BaseModelResource, BaseModelsResource
from zou.app import name_space_output_types


@name_space_output_types.route('/')
class OutputTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, OutputType)

    def check_read_permissions(self):
        return True


@name_space_output_types.route('/<instance_id>')
class OutputTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, OutputType)

    def check_read_permissions(self, instance):
        return True
