from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/search_filter_group.yml")


class SearchFilterGroupsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilterGroup)

    @jwt_required()
    @swag_from(SPECS["SearchFilterGroupsResource_get"])
    def get(self):
        """
        Get search filter groups
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["SearchFilterGroupsResource_post"])
    def post(self):
        """
        Create search filter group
        """
        return super().post()


class SearchFilterGroupResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilterGroup)

    @jwt_required()
    @swag_from(SPECS["SearchFilterGroupResource_get"])
    def get(self, instance_id):
        """
        Get search filter group
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["SearchFilterGroupResource_put"])
    def put(self, instance_id):
        """
        Update search filter group
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["SearchFilterGroupResource_delete"])
    def delete(self, instance_id):
        """
        Delete search filter group
        """
        return super().delete(instance_id)
