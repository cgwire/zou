from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.task_status import TaskStatus
from zou.app.services import (
    task_types_service,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/task_status.yml")


class TaskStatusesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskStatus)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["TaskStatusesResource_get"])
    def get(self):
        """
        Get task statuses
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["TaskStatusesResource_post"])
    def post(self):
        """
        Create task status
        """
        return super().post()

    def post_creation(self, instance):
        task_types_service.clear_task_status_cache(str(instance.id))
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
    @swag_from(SPECS["TaskStatusResource_get"])
    def get(self, instance_id):
        """
        Get task status
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["TaskStatusResource_put"])
    def put(self, instance_id):
        """
        Update task status
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["TaskStatusResource_delete"])
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
        task_types_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        task_types_service.clear_task_status_cache(instance_dict["id"])
        return instance_dict
