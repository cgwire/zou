from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.hardware_item import HardwareItem
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/hardware_item.yml")


class HardwareItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, HardwareItem)

    @jwt_required()
    @swag_from(SPECS["HardwareItemsResource_get"])
    def get(self):
        """
        Get hardware items
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["HardwareItemsResource_post"])
    def post(self):
        """
        Create hardware item
        """
        return super().post()


class HardwareItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, HardwareItem)

    @jwt_required()
    @swag_from(SPECS["HardwareItemResource_get"])
    def get(self, instance_id):
        """
        Get hardware item
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["HardwareItemResource_put"])
    def put(self, instance_id):
        """
        Update hardware item
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["HardwareItemResource_delete"])
    def delete(self, instance_id):
        """
        Delete hardware item
        """
        return super().delete(instance_id)
