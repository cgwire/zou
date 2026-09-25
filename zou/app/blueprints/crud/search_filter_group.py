from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.search_filter_group import SearchFilterGroup

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class SearchFilterGroupsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SearchFilterGroup)

    @jwt_required()
    @swag_from("openapi/SearchFilterGroupsResource_get.yml")
    def get(self):
        """
        Get search filter groups
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/SearchFilterGroupsResource_post.yml")
    def post(self):
        """
        Create search filter group
        """
        return super().post()


class SearchFilterGroupResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SearchFilterGroup)

    @jwt_required()
    @swag_from("openapi/SearchFilterGroupResource_get.yml")
    def get(self, instance_id):
        """
        Get search filter group
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/SearchFilterGroupResource_put.yml")
    def put(self, instance_id):
        """
        Update search filter group
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/SearchFilterGroupResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete search filter group
        """
        return super().delete(instance_id)
