from zou.app.models.day_off import DayOff
from zou.app.models.time_spent import TimeSpent

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import user_service


class DayOffsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, DayOff)

    def check_create_permissions(self, data):
        return user_service.check_day_off_access(data)

    def post_creation(self, instance):
        if instance.end_date:
            TimeSpent.delete_all_by(
                instance.date >= TimeSpent.date,
                instance.end_date <= TimeSpent.date,
                person_id=instance.person_id,
            )
        else:
            TimeSpent.delete_all_by(
                person_id=instance.person_id, date=instance.date
            )
        return instance.serialize()


class DayOffResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, DayOff)

    def check_delete_permissions(self, instance_dict):
        return user_service.check_day_off_access(instance_dict)

    def check_read_permissions(self, instance):
        return user_service.check_day_off_access(instance)

    def post_update(self, instance_dict, data):
        if "end_date" in data and data["end_date"]:
            TimeSpent.delete_all_by(
                instance_dict["date"] >= TimeSpent.date,
                instance_dict["end_date"] <= TimeSpent.date,
                person_id=instance_dict["person_id"],
            )
        elif "date" in data:
            TimeSpent.delete_all_by(
                person_id=instance_dict["person_id"],
                date=instance_dict["date"],
            )
        return instance_dict
