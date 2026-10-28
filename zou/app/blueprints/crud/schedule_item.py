from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.schedule_item import ScheduleItem
from zou.app.services import permissions_service, user_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/schedule_item.yml")


class ScheduleItemsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ScheduleItem)

    @jwt_required()
    @swag_from(SPECS["ScheduleItemsResource_get"])
    def get(self):
        """
        Get schedule items
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["ScheduleItemsResource_post"])
    def post(self):
        """
        Create schedule item
        """
        return super().post()

    def check_create_permissions(self, data):
        return permissions_service.check_manager_project_access(
            data.get("project_id")
        )

    def check_creation_integrity(self, data):
        schedule_item = ScheduleItem.get_by(
            project_id=data.get("project_id", None),
            task_type_id=data.get("task_type_id", None),
            object_id=data.get("object_id", None),
        )
        if schedule_item is not None:
            raise WrongParameterException(
                "A similar schedule item already exists"
            )
        return schedule_item


class ScheduleItemResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ScheduleItem)

    def check_update_permissions(self, instance, data):
        return permissions_service.check_supervisor_project_task_type_access(
            instance["project_id"], instance["task_type_id"]
        )

    def check_delete_permissions(self, instance_dict):
        return permissions_service.check_manager_project_access(
            instance_dict["project_id"]
        )

    @jwt_required()
    @swag_from(SPECS["ScheduleItemResource_get"])
    def get(self, instance_id):
        """
        Get schedule item
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["ScheduleItemResource_put"])
    def put(self, instance_id):
        """
        Update schedule item
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["ScheduleItemResource_delete"])
    def delete(self, instance_id):
        """
        Delete schedule item
        """
        return super().delete(instance_id)

    def update_data(self, data, instance_id):
        data = super().update_data(data, instance_id)
        if isinstance(data.get("man_days", None), str):
            data.pop("man_days", None)

        for field in self.protected_fields:
            data.pop(field, None)

        return data
