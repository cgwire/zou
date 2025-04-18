from zou.app.models.plugin import Plugin

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class PluginsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Plugin)


class PluginResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Plugin)
