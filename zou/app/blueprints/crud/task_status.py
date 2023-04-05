from zou.app.models.task_status import TaskStatus
from zou.app.services import tasks_service
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class TaskStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskStatus)

    def check_read_permissions(self):
        return True

    def post_creation(self, instance):
        tasks_service.clear_task_status_cache(str(instance.id))
        return instance.serialize()

    def check_creation_integrity(self, data):
        if data.get("is_default", False):
            status = TaskStatus.get_by(is_default=True)
            if status:
                status.update({"is_default": False})
        return data


class TaskStatusResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskStatus)

    def check_read_permissions(self, instance):
        return True

    def pre_update(self, instance_dict, data):
        if data.get("is_default", False):
            status = TaskStatus.get_by(is_default=True)
            if status:
                status.update({"is_default": False})
        return instance_dict

    def post_update(self, instance_dict):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict
