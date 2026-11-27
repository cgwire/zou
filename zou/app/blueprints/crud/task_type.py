from flask import request
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.task_type import TaskType
from zou.app.services import (
    status_automations_service,
    task_types_service,
)
from zou.app.utils import fields, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/task_type.yml")


class TaskTypesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, TaskType)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["TaskTypesResource_get"])
    def get(self):
        """
        Get task types
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["TaskTypesResource_post"])
    def post(self):
        """
        Create task type
        """
        return super().post()

    def update_data(self, data):
        data = super().update_data(data)
        task_types_service.check_task_type_name_is_unique(data.get("name"))
        return data

    def post_creation(self, instance):
        task_types_service.clear_task_type_cache(str(instance.id))
        return instance.serialize(relations=True)


class TaskTypeResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, TaskType)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from(SPECS["TaskTypeResource_get"])
    def get(self, instance_id):
        """
        Get task type
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["TaskTypeResource_put"])
    def put(self, instance_id):
        """
        Update task type
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["TaskTypeResource_delete"])
    def delete(self, instance_id):
        """
        Delete task type
        """
        return super().delete(instance_id)

    def pre_delete(self, instance_dict):
        """
        If the task type has scheduled items or is linked to projects, refuse
        the delete with a clear 400, unless ``force`` is set. With force, the
        function deletes those rows first, so that their foreign keys do not
        block the deletion. If a status automation uses the task type, the
        delete fails, also with force.
        """
        status_automations_service.guard_task_type_deletion(instance_dict)
        task_type_id = instance_dict["id"]
        if self.get_force():
            task_types_service.detach_task_type_no_commit(task_type_id)
            return instance_dict

        blockers = []
        if task_types_service.is_task_type_scheduled(task_type_id):
            blockers.append("schedule items")
        if task_types_service.is_task_type_in_projects(task_type_id):
            blockers.append("projects")
        if blockers:
            raise WrongParameterException(
                f"Task type is attached to {' and '.join(blockers)}. "
                "Re-issue the request with force=true to detach."
            )
        return instance_dict

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        # Check only a change of name. The clients send the full form at each
        # update. Thus users must be able to change the color or the department
        # of a row that already has a case twin, and keep its name.
        name = data.get("name", None)
        if name is not None and name != self.instance.name:
            task_types_service.check_task_type_name_is_unique(
                name, exclude_task_type_id=instance_id
            )
        return data

    def post_update(self, instance_dict, data):
        task_types_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        task_types_service.clear_task_type_cache(instance_dict["id"])
        return instance_dict


class TaskTypesReorderResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["TaskTypesReorderResource_post"])
    def post(self):
        """
        Reorder task types
        """
        permissions.check_admin_permissions()
        body = request.json
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("task_type_ids"), list)
            or not all(map(fields.is_valid_id, body["task_type_ids"]))
        ):
            raise WrongParameterException(
                "Request body must be a JSON object with a "
                "'task_type_ids' list of task type IDs."
            )
        return task_types_service.reorder_task_types(body["task_type_ids"])
