from zou.app.models.entity import EntityLink
from zou.app.utils import fields

from .base import BaseModelResource, BaseModelsResource
from zou.app.services.exception import (
    EntityLinkNotFoundException,
    WrongParameterException
)


class EntityLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityLink)


class EntityLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityLink)

    def get_model_or_404(self, instance_id):
        if not fields.is_valid_id(instance_id):
            raise WrongParameterException("Malformed ID.")
        instance = self.model.get_by(id=instance_id)
        if instance is None:
            raise EntityLinkNotFoundException
        return instance
