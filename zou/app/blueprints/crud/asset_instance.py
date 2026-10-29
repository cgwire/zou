from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.asset_instance import AssetInstance
from zou.app.services import assets_service, permissions_service, user_service
from zou.app.utils import permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/asset_instance.yml")


class AssetInstancesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, AssetInstance)

    @jwt_required()
    @swag_from(SPECS["AssetInstancesResource_get"])
    def get(self):
        """
        Get asset instances
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["AssetInstancesResource_post"])
    def post(self):
        """
        Create asset instance
        """
        return super().post()


class AssetInstanceResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, AssetInstance)
        # The update check reads the project off the stored asset.
        self.protected_fields += [
            "number",
            "asset_id",
            "scene_id",
            "target_asset_id",
        ]

    @jwt_required()
    @swag_from(SPECS["AssetInstanceResource_get"])
    def get(self, instance_id):
        """
        Get asset instance
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["AssetInstanceResource_put"])
    def put(self, instance_id):
        """
        Update asset instance
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["AssetInstanceResource_delete"])
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
            permissions_service.check_project_edition_access(
                asset["project_id"]
            )
            return True
