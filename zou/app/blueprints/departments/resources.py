from flasgger import swag_from
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.exceptions import SoftwareNotFoundException
from zou.app.utils import permissions, validation
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    departments_service,
)
from zou.app.blueprints.departments.schemas import (
    AddSoftwareToDepartmentSchema,
    AddHardwareToDepartmentSchema,
)


class AllDepartmentSoftwareResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/AllDepartmentSoftwareResource_get.yml")
    def get(self):
        """
        Get all department software licenses
        """
        softwares = departments_service.get_all_software_for_departments()
        return softwares, 200


class AddSoftwareToDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/AddSoftwareToDepartmentResource_post.yml")
    def post(self, department_id):
        """
        Add software license to department
        """
        body = validation.validate_request_body(AddSoftwareToDepartmentSchema)
        self.check_id_parameter(department_id)
        software = departments_service.add_software_to_department(
            department_id, str(body.software_id)
        )
        return software, 201


class SoftwareDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/SoftwareDepartmentResource_get.yml")
    def get(self, department_id, software_id):
        """
        Get department software license
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(software_id)
        for software in departments_service.get_software_for_department(
            department_id
        ):
            if software["id"] == software_id:
                return software, 200
        raise SoftwareNotFoundException

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/SoftwareDepartmentResource_delete.yml")
    def delete(self, department_id, software_id):
        """
        Remove software license from department
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(software_id)
        departments_service.remove_software_from_department(
            department_id, software_id
        )
        return "", 204


class AllDepartmentHardwareItemsResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/AllDepartmentHardwareItemsResource_get.yml")
    def get(self):
        """
        Get all department hardware items
        """
        hardware_items = (
            departments_service.get_all_hardware_items_for_departments()
        )
        return hardware_items, 200


class AddHardwareItemToDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/AddHardwareItemToDepartmentResource_post.yml")
    def post(self, department_id):
        """
        Add hardware item to department
        """
        body = validation.validate_request_body(AddHardwareToDepartmentSchema)
        self.check_id_parameter(department_id)
        hardware_item_link = (
            departments_service.add_hardware_item_to_department(
                department_id, str(body.hardware_item_id)
            )
        )
        return hardware_item_link, 201


class HardwareItemDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/HardwareItemDepartmentResource_get.yml")
    def get(self, department_id):
        """
        Get department hardware items
        """
        self.check_id_parameter(department_id)
        hardware_items = departments_service.get_hardware_items_for_department(
            department_id
        )
        return hardware_items, 200

    @jwt_required()
    @permissions.require_admin
    @swag_from("openapi/HardwareItemDepartmentResource_delete.yml")
    def delete(self, department_id, hardware_item_id):
        """
        Remove hardware item from department
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(hardware_item_id)
        departments_service.remove_hardware_item_from_department(
            department_id, hardware_item_id
        )
        return "", 204


class DepartmentPersonsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/DepartmentPersonsResource_get.yml")
    def get(self, department_id):
        """
        Get department members
        """
        self.check_id_parameter(department_id)
        persons = departments_service.get_persons_for_department(
            department_id, minimal=not permissions.has_admin_permissions()
        )
        return persons, 200
