from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.plugin import Plugin

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


class PluginsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Plugin)

    @jwt_required()
    @swag_from("openapi/PluginsResource_get.yml")
    def get(self):
        """
        Get plugins
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/PluginsResource_post.yml")
    def post(self):
        """
        Create plugin
        """
        return super().post()


class PluginResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Plugin)

    @jwt_required()
    @swag_from("openapi/PluginResource_get.yml")
    def get(self, instance_id):
        """
        Get plugin
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/PluginResource_put.yml")
    def put(self, instance_id):
        """
        Update plugin
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/PluginResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete plugin
        """
        return super().delete(instance_id)
