from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.search_filter import SearchFilter

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class SearchFiltersResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilter)

    @jwt_required()
    @swag_from("openapi/SearchFiltersResource_get.yml")
    def get(self):
        """
        Get search filters
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/SearchFiltersResource_post.yml")
    def post(self):
        """
        Create search filter
        """
        return super().post()


class SearchFilterResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilter)

    @jwt_required()
    @swag_from("openapi/SearchFilterResource_get.yml")
    def get(self, instance_id):
        """
        Get search filter
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/SearchFilterResource_put.yml")
    def put(self, instance_id):
        """
        Update search filter
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/SearchFilterResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete search filter
        """
        return super().delete(instance_id)
