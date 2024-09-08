from zou.app.models.schedule_item import ScheduleItem

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource

from zou.app.services import user_service
from zou.app.services.exception import WrongParameterException


class ScheduleItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ScheduleItem)

    def check_creation_integrity(self, data):
        schedule_item = ScheduleItem.get_by(
            project_id=data.get("project_id", None),
            task_type_id=data.get("task_type_id", None),
            object_id=data.get("object_id", None),
        )
        if schedule_item is not None:
            raise WrongParameterException("A similar schedule item already exists")
        return schedule_item


class ScheduleItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ScheduleItem)

    def check_update_permissions(self, instance, data):
        return user_service.check_supervisor_schedule_item_access(
            instance, data
        )

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if isinstance(data.get("man_days", None), str):
            data.pop("man_days", None)

        for field in self.protected_fields:
            data.pop(field, None)

        return data
