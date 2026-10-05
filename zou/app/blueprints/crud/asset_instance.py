from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.asset_instance import AssetInstance

from zou.app.services import assets_service, permissions_service, user_service
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class AssetInstancesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AssetInstance)

    @jwt_required()
    @swag_from("openapi/AssetInstancesResource_get.yml")
    def get(self):
        """
        Get asset instances
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/AssetInstancesResource_post.yml")
    def post(self):
        """
        Create asset instance
        """
        return super().post()


class AssetInstanceResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AssetInstance)
        self.protected_fields.append("number")

    @jwt_required()
    @swag_from("openapi/AssetInstanceResource_get.yml")
    def get(self, instance_id):
        """
        Get asset instance
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/AssetInstanceResource_put.yml")
    def put(self, instance_id):
        """
        Update asset instance
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/AssetInstanceResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete asset instance
        """
        return super().delete(instance_id)

    def check_read_permissions(self, instance):
        if permissions.has_admin_permissions():
            return True
        else:
            asset_instance = self.get_model_or_404(instance["id"])
            asset = assets_service.get_asset(asset_instance.asset_id)
            permissions_service.check_project_access(asset["project_id"])
            permissions_service.check_entity_access(asset["id"])
            return True

    def check_update_permissions(self, asset_instance, data):
        if permissions.has_admin_permissions():
            return True
        else:
            asset = assets_service.get_asset(asset_instance["asset_id"])
            permissions_service.check_project_access(asset["project_id"])
            permissions_service.check_entity_access(asset["id"])
            return True
