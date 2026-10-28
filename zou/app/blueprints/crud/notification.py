from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.notification import Notification
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/notification.yml")


class NotificationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Notification)

    @jwt_required()
    @swag_from(SPECS["NotificationsResource_get"])
    def get(self):
        """
        Get notifications
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["NotificationsResource_post"])
    def post(self):
        """
        Create notification
        """
        return super().post()


class NotificationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Notification)

    @jwt_required()
    @swag_from(SPECS["NotificationResource_get"])
    def get(self, instance_id):
        """
        Get notification
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["NotificationResource_put"])
    def put(self, instance_id):
        """
        Update notification
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["NotificationResource_delete"])
    def delete(self, instance_id):
        """
        Delete notification
        """
        return super().delete(instance_id)
