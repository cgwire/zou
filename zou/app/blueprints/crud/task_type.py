from flask_jwt_extended import jwt_required
from sqlalchemy.exc import StatementError

from zou.app.models.entity_type import EntityType
from zou.app.models.task_type import TaskType
from zou.app.services.exception import ArgumentsException, TaskTypeNotFoundException
from zou.app.services import tasks_service

from .base import BaseModelResource, BaseModelsResource


class TaskTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskType)

    def all_entries(self, query=None):
        if query is None:
            query = self.model.query

        return [
                    task_type.serialize(relations=True) for task_type in query.all()
                ]

    def check_read_permissions(self):
        return True

    def update_data(self, data):
        name = data.get("name", None)
        task_type = TaskType.get_by(name=name)
        if task_type is not None:
            raise ArgumentsException(
                "A task type with similar name already exists"
            )
        
        # Handle asset types the task type is dedicated to
        data["asset_types"] = tasks_service.get_asset_types_from_task_type(data)
        
        return data

    def post_creation(self, instance):
        tasks_service.clear_task_type_cache(str(instance.id))
        return instance.serialize()


class TaskTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskType)

    def check_read_permissions(self, instance):
        return True

    def update_data(self, data, instance_id):
        name = data.get("name", None)
        if name is not None:
            task_type = TaskType.get_by(name=name)
            if task_type is not None and instance_id != str(task_type.id):
                raise ArgumentsException(
                    "A task type with similar name already exists"
                )

        # Handle asset types the task type is dedicated to
        data["asset_types"] = tasks_service.get_asset_types_from_task_type(data)
        
        return data

    def post_update(self, instance_dict):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        instance_dict["asset_types"] = [
            str(asset_types.id) for asset_types in self.instance.asset_types
        ]
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict
