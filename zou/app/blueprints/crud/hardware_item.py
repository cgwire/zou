from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.hardware_item import HardwareItem
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class HardwareItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, HardwareItem)

    @jwt_required()
    @swag_from("openapi/HardwareItemsResource_get.yml")
    def get(self):
        """
        Get hardware items
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/HardwareItemsResource_post.yml")
    def post(self):
        """
        Create hardware item
        """
        return super().post()


class HardwareItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, HardwareItem)

    @jwt_required()
    @swag_from("openapi/HardwareItemResource_get.yml")
    def get(self, instance_id):
        """
        Get hardware item
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/HardwareItemResource_put.yml")
    def put(self, instance_id):
        """
        Update hardware item
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/HardwareItemResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete hardware item
        """
        return super().delete(instance_id)
