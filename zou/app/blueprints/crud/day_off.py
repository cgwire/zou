from zou.app.models.day_off import DayOff
from zou.app.models.time_spent import TimeSpent

from .base import BaseModelsResource, BaseModelResource

from zou.app.services import user_service
from zou.app.utils import date_helpers, permissions


class DayOffsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, DayOff)

    def check_create_permissions(self, data):
        return user_service.check_day_off_access(data)

    def update_data(self, data):
        data["date"] = date_helpers.get_date_from_string(data["date"])
        return data

    def post_creation(self, instance):
        time_spents = TimeSpent.delete_all_by(
            person_id=instance.person_id, date=instance.date
        )
        return instance.serialize()


class DayOffResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, DayOff)

    def check_delete_permissions(self, instance):
        return user_service.check_day_off_access(instance)

    def check_read_permissions(self, instance):
        return user_service.check_day_off_access(instance)
