from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.plugin import Plugin
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/plugin.yml")


class PluginsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Plugin)

    @jwt_required()
    @swag_from(SPECS["PluginsResource_get"])
    def get(self):
        """
        Get plugins
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["PluginsResource_post"])
    def post(self):
        """
        Create plugin
        """
        return super().post()


class PluginResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Plugin)

    @jwt_required()
    @swag_from(SPECS["PluginResource_get"])
    def get(self, instance_id):
        """
        Get plugin
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["PluginResource_put"])
    def put(self, instance_id):
        """
        Update plugin
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["PluginResource_delete"])
    def delete(self, instance_id):
        """
        Delete plugin
        """
        return super().delete(instance_id)
