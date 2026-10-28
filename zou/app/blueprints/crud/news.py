from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.news import News
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/news.yml")


class NewssResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, News)

    @jwt_required()
    @swag_from(SPECS["NewssResource_get"])
    def get(self):
        """
        Get news
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["NewssResource_post"])
    def post(self):
        """
        Create news
        """
        return super().post()


class NewsResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, News)

    @jwt_required()
    @swag_from(SPECS["NewsResource_get"])
    def get(self, instance_id):
        """
        Get news
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["NewsResource_put"])
    def put(self, instance_id):
        """
        Update news
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["NewsResource_delete"])
    def delete(self, instance_id):
        """
        Delete news
        """
        return super().delete(instance_id)
