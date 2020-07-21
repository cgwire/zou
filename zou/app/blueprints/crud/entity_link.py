from zou.app.models.entity import EntityLink

from .base import BaseModelResource, BaseModelsResource


class EntityLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityLink)


class EntityLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityLink)
