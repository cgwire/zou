from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import (
    permissions_service,
    schedule_service,
    tasks_service,
    user_service,
)
from zou.app.utils import fields, permissions
from zou.app.exceptions import WrongParameterException


class ProductionScheduleVersionsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, options=None):
        if options and "project_id" in options:
            permissions_service.check_project_access(options["project_id"])
        else:
            permissions.check_admin_permissions()
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionsResource_get.yml")
    def get(self):
        """
        Get production schedule versions
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionsResource_post.yml")
    def post(self):
        """
        Create production schedule version
        """
        return super().post()

    def check_create_permissions(self, data):
        return permissions_service.check_manager_project_access(
            project_id=data["project_id"]
        )


class ProductionScheduleVersionResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, ProductionScheduleVersion)

    def check_read_permissions(self, instance_dict):
        permissions_service.check_project_access(instance_dict["project_id"])
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionResource_get.yml")
    def get(self, instance_id):
        """
        Get production schedule version
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionResource_put.yml")
    def put(self, instance_id):
        """
        Update production schedule version
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete production schedule version
        """
        return super().delete(instance_id)

    def check_update_permissions(self, instance_dict, data):
        return permissions_service.check_manager_project_access(
            project_id=instance_dict["project_id"]
        )

    def check_delete_permissions(self, instance_dict):
        return permissions_service.check_manager_project_access(
            project_id=instance_dict["project_id"]
        )

    def pre_delete(self, instance_dict):
        schedule_service.detach_production_schedule_version(
            instance_dict["id"]
        )
        return instance_dict


class ProductionScheduleVersionTaskLinksResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, ProductionScheduleVersionTaskLink)

    def get_relations_eager_load(self):
        return [ProductionScheduleVersionTaskLink.assignees]

    def check_read_permissions(self, options=None):
        if options and "project_id" in options:
            permissions_service.check_project_access(options["project_id"])
        else:
            permissions.check_admin_permissions()
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

    def apply_filters(self, query, options):
        # A task link has no project_id column, so the generic filters drop
        # the parameter the read check was granted on: scope the rows to
        # that project through their version.
        query = super().apply_filters(query, options)
        if "project_id" in options:
            if not fields.is_valid_id(options["project_id"]):
                raise WrongParameterException("Invalid project_id.")
            link = ProductionScheduleVersionTaskLink
            query = query.join(
                ProductionScheduleVersion,
                ProductionScheduleVersion.id
                == link.production_schedule_version_id,
            ).filter(
                ProductionScheduleVersion.project_id == options["project_id"]
            )
        return query

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinksResource_get.yml")
    def get(self):
        """
        Get production schedule version task links
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinksResource_post.yml")
    def post(self):
        """
        Create production schedule version task link
        """
        return super().post()

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
        return permissions_service.check_manager_project_access(
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
        task = tasks_service.get_task(instance_dict["task_id"])
        permissions_service.check_project_access(task["project_id"])
        if (
            permissions.has_vendor_permissions()
            or permissions.has_client_permissions()
        ):
            raise permissions.PermissionDenied

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinkResource_get.yml")
    def get(self, instance_id):
        """
        Get production schedule version task link
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinkResource_put.yml")
    def put(self, instance_id):
        """
        Update production schedule version task link
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/ProductionScheduleVersionTaskLinkResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete production schedule version task link
        """
        return super().delete(instance_id)

    def check_update_permissions(self, instance_dict, data):
        task = tasks_service.get_task(instance_dict["task_id"])
        return permissions_service.check_manager_project_access(
            project_id=task["project_id"]
        )

    def check_delete_permissions(self, instance_dict):
        task = tasks_service.get_task(instance_dict["task_id"])
        return permissions_service.check_manager_project_access(
            project_id=task["project_id"]
        )
