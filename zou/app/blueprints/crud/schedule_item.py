from zou.app.models.schedule_item import ScheduleItem

from .base import BaseModelResource, BaseModelsResource

from zou.app.services import user_service


class ScheduleItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ScheduleItem)


class ScheduleItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ScheduleItem)

    def check_update_permissions(self, instance, data):
        return user_service.check_manager_project_access(instance["project_id"])

    def update_data(self, data, instance_id):
        if isinstance(data.get("man_days", None), str):
            data.pop("man_days", None)

        for field in self.protected_fields:
            data.pop(field, None)

        return data
