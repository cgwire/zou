from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services import user_service, tasks_service

from zou.app.utils import permissions


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

    def pre_delete(self, instance_dict):
        ProductionScheduleVersionTaskLink.delete_all_by(
            production_schedule_version_id=instance_dict["id"]
        )
        return True


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

    def delete(self, instance_id):
        raise AttributeError("Method not allowed")
