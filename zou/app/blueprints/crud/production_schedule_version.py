from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import user_service, tasks_service, schedule_service
from zou.app.utils import permissions
from zou.app.services.exception import WrongParameterException


class ProductionScheduleVersionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, options=None):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        if "project_id" in options.keys():
            return user_service.check_project_access(options["project_id"])
        else:
            return permissions.check_admin_permissions()

    def check_create_permissions(self, data):
        return user_service.check_manager_project_access(
            project_id=data["project_id"]
        )


class ProductionScheduleVersionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, instance_dict):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        return user_service.check_project_access(instance_dict["project_id"])

    def check_update_permissions(self, instance_dict, data):
        return user_service.check_manager_project_access(
            project_id=instance_dict["project_id"]
        )


class ProductionScheduleVersionTaskLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersionTaskLink)

    def check_read_permissions(self, options=None):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        if "project_id" in options.keys():
            return user_service.check_project_access(options["project_id"])
        else:
            return permissions.check_admin_permissions()

    def check_create_permissions(self, data):
        project_id_from_production_version_schedule = (
            schedule_service.get_production_schedule_version(
                data["production_schedule_version_id"]
            )["project_id"]
        )
        project_id_from_task = tasks_service.get_task(data["task_id"])[
            "project_id"
        ]
        if project_id_from_production_version_schedule != project_id_from_task:
            raise WrongParameterException(
                "The task and the production schedule version must be in the same project."
            )
        return user_service.check_manager_project_access(
            project_id=project_id_from_production_version_schedule
        )


class ProductionScheduleVersionTaskLinkResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProductionScheduleVersionTaskLink)
        self.protected_fields = [
            "id",
            "created_at",
            "updated_at",
            "task_id",
            "production_schedule_version_id",
        ]

    def check_read_permissions(self, instance_dict):
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_project_access(task["project_id"])

    def check_update_permissions(self, instance_dict, data):
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_manager_project_access(
            project_id=task["project_id"]
        )

    def check_delete_permissions(self, instance_dict):
        task = tasks_service.get_task(instance_dict["task_id"])
        return user_service.check_manager_project_access(
            project_id=task["project_id"]
        )
