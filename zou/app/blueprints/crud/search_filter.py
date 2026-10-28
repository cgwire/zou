from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.search_filter import SearchFilter
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/search_filter.yml")


class SearchFiltersResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilter)

    @jwt_required()
    @swag_from(SPECS["SearchFiltersResource_get"])
    def get(self):
        """
        Get search filters
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["SearchFiltersResource_post"])
    def post(self):
        """
        Create search filter
        """
        return super().post()


class SearchFilterResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilter)

    @jwt_required()
    @swag_from(SPECS["SearchFilterResource_get"])
    def get(self, instance_id):
        """
        Get search filter
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["SearchFilterResource_put"])
    def put(self, instance_id):
        """
        Update search filter
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["SearchFilterResource_delete"])
    def delete(self, instance_id):
        """
        Delete search filter
        """
        return super().delete(instance_id)
