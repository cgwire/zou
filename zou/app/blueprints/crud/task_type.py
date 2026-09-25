from flasgger import swag_from
from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.models.task_type import TaskType
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.exceptions import WrongParameterException
from zou.app.services import tasks_service
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource


class TaskTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskType)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from("openapi/TaskTypesResource_get.yml")
    def get(self):
        """
        Get task types
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/TaskTypesResource_post.yml")
    def post(self):
        """
        Create task type
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        tasks_service.check_task_type_name_is_unique(data.get("name"))
        return data

    def post_creation(self, instance):
        tasks_service.clear_task_type_cache(str(instance.id))
        return instance.serialize(relations=True)


class TaskTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from("openapi/TaskTypeResource_get.yml")
    def get(self, instance_id):
        """
        Get task type
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/TaskTypeResource_put.yml")
    def put(self, instance_id):
        """
        Update task type
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/TaskTypeResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete task type
        """
        return super().delete(instance_id)

    def pre_delete(self, instance_dict):
        """
        Refuse the delete with a clean 400 when the task type still has
        scheduled items or is attached to projects, unless ``force`` is
        set. With force, those rows are purged first so the deletion is
        not blocked by their foreign keys.
        """
        task_type_id = instance_dict["id"]
        if self.get_force():
            ScheduleItem.query.filter_by(task_type_id=task_type_id).delete()
            ProjectTaskTypeLink.query.filter_by(
                task_type_id=task_type_id
            ).delete()
            return instance_dict

        blockers = []
        if ScheduleItem.query.filter_by(task_type_id=task_type_id).count():
            blockers.append("schedule items")
        if ProjectTaskTypeLink.query.filter_by(
            task_type_id=task_type_id
        ).count():
            blockers.append("projects")
        if blockers:
            raise WrongParameterException(
                f"Task type is attached to {' and '.join(blockers)}. "
                "Re-issue the request with force=true to detach."
            )
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        # only a change of name is checked: the clients send the whole
        # form on every update, so a row already carrying a case twin
        # must stay editable (colour, department) without renaming it
        name = data.get("name", None)
        if name is not None and name != self.instance.name:
            tasks_service.check_task_type_name_is_unique(
                name, exclude_task_type_id=instance_id
            )
        return data

    def post_update(self, instance_dict, data):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        tasks_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict


class TaskTypesReorderResource(MethodView):
    @jwt_required()
    @swag_from("openapi/TaskTypesReorderResource_post.yml")
    def post(self):
        """
        Reorder task types
        """
        permissions.check_admin_permissions()
        body = request.json
        if not isinstance(body, dict) or not isinstance(
            body.get("task_type_ids"), list
        ):
            raise WrongParameterException(
                "Request body must be a JSON object with a "
                "'task_type_ids' list."
            )
        updated = []
        for priority, task_type_id in enumerate(
            body["task_type_ids"], start=1
        ):
            task_type = TaskType.get(task_type_id)
            if task_type is not None:
                task_type.update({"priority": priority})
                tasks_service.clear_task_type_cache(str(task_type.id))
                updated.append(task_type.serialize())
        return updated
