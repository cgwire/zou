from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.news import News

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class NewssResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, News)

    @jwt_required()
    @swag_from("openapi/NewssResource_get.yml")
    def get(self):
        """
        Get news
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/NewssResource_post.yml")
    def post(self):
        """
        Create news
        """
        return super().post()


class NewsResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, News)

    @jwt_required()
    @swag_from("openapi/NewsResource_get.yml")
    def get(self, instance_id):
        """
        Get news
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/NewsResource_put.yml")
    def put(self, instance_id):
        """
        Update news
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/NewsResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete news
        """
        return super().delete(instance_id)
