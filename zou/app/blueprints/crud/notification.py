from zou.app.models.notification import Notification
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class NotificationsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Notification)

    def check_create_permissions(self, data):
        return permissions.check_admin_permissions()


class NotificationResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Notification)
