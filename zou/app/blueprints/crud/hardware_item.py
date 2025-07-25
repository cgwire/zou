from zou.app.models.hardware_item import HardwareItem
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class HardwareItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, HardwareItem)


class HardwareItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, HardwareItem)
