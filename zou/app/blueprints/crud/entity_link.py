from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.entity import EntityLink
from zou.app.utils import fields

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import (
    EntityLinkNotFoundException,
    WrongParameterException,
)


class EntityLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, EntityLink)

    @jwt_required()
    @swag_from("openapi/EntityLinksResource_get.yml")
    def get(self):
        """
        Get entity links
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/EntityLinksResource_post.yml")
    def post(self):
        """
        Create entity link
        """
        return super().post()


class EntityLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, EntityLink)

    @jwt_required()
    @swag_from("openapi/EntityLinkResource_get.yml")
    def get(self, instance_id):
        """
        Get entity link
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/EntityLinkResource_put.yml")
    def put(self, instance_id):
        """
        Update entity link
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/EntityLinkResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete entity link
        """
        return super().delete(instance_id)

    def get_model_or_404(self, instance_id):
        if not fields.is_valid_id(instance_id):
            raise WrongParameterException("Malformed ID.")
        instance = self.model.get_by(id=instance_id)
        if instance is None:
            raise EntityLinkNotFoundException
        return instance
