from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.task_status import TaskStatus
from zou.app.services import tasks_service
from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class TaskStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskStatus)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/TaskStatusesResource_get.yml")
    def get(self):
        """
        Get task statuses
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/TaskStatusesResource_post.yml")
    def post(self):
        """
        Create task status
        """
        return super().post()

    def post_creation(self, instance):
        tasks_service.clear_task_status_cache(str(instance.id))
        return instance.serialize(relations=True)

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

    @jwt_required()
    @swag_from("openapi/TaskStatusResource_get.yml")
    def get(self, instance_id):
        """
        Get task status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/TaskStatusResource_put.yml")
    def put(self, instance_id):
        """
        Update task status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/TaskStatusResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete task status
        """
        return super().delete(instance_id)

    def pre_update(self, instance_dict, data):
        if data.get("is_default", False):
            status = TaskStatus.get_by(is_default=True)
            if status:
                status.update({"is_default": False})
        return instance_dict

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict
