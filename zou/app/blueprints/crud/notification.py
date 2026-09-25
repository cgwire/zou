from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.notification import Notification

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class NotificationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Notification)

    @jwt_required()
    @swag_from("openapi/NotificationsResource_get.yml")
    def get(self):
        """
        Get notifications
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/NotificationsResource_post.yml")
    def post(self):
        """
        Create notification
        """
        return super().post()


class NotificationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Notification)

    @jwt_required()
    @swag_from("openapi/NotificationResource_get.yml")
    def get(self, instance_id):
        """
        Get notification
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/NotificationResource_put.yml")
    def put(self, instance_id):
        """
        Update notification
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/NotificationResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete notification
        """
        return super().delete(instance_id)
