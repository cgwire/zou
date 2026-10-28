from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.department import Department
from zou.app.services import (
    departments_service,
)
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/department.yml")


class DepartmentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Department)

    def check_read_permissions(self, options=None):
        return True

    @jwt_required()
    @swag_from(SPECS["DepartmentsResource_get"])
    def get(self):
        """
        Get departments
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["DepartmentsResource_post"])
    def post(self):
        """
        Create department
        """
        return super().post()

    def post_creation(self, instance):
        departments_service.clear_department_cache(str(instance.id))
        return instance.serialize(relations=True)


class DepartmentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Department)

    def check_read_permissions(self, instance):
        return True

    @jwt_required()
    @swag_from(SPECS["DepartmentResource_get"])
    def get(self, instance_id):
        """
        Get department
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["DepartmentResource_put"])
    def put(self, instance_id):
        """
        Update department
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["DepartmentResource_delete"])
    def delete(self, instance_id):
        """
        Delete department
        """
        return super().delete(instance_id)

    def post_update(self, instance_dict, data):
        departments_service.clear_department_cache(instance_dict["id"])
        return instance_dict

    def post_delete(self, instance_dict):
        departments_service.clear_department_cache(instance_dict["id"])
        return instance_dict
