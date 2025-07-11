from zou.app.models.notification import Notification

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class NotificationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Notification)


class NotificationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Notification)
