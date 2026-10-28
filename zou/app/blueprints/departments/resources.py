from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.blueprints.departments.schemas import (
    AddHardwareToDepartmentSchema,
    AddSoftwareToDepartmentSchema,
)
from zou.app.exceptions import (
    HardwareItemNotFoundException,
    SoftwareNotFoundException,
)
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    departments_service,
    permissions_service,
)
from zou.app.utils import permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class AllDepartmentSoftwareResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from(SPECS["AllDepartmentSoftwareResource_get"])
    def get(self):
        """
        Get all department software licenses
        """
        softwares = departments_service.get_all_software_for_departments()
        return softwares, 200


class AddSoftwareToDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    @swag_from(SPECS["AddSoftwareToDepartmentResource_post"])
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
    @swag_from(SPECS["SoftwareDepartmentResource_get"])
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
    @swag_from(SPECS["SoftwareDepartmentResource_delete"])
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
    @swag_from(SPECS["AllDepartmentHardwareItemsResource_get"])
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
    @swag_from(SPECS["AddHardwareItemToDepartmentResource_post"])
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
    @swag_from(SPECS["HardwareItemDepartmentResource_get"])
    def get(self, department_id, hardware_item_id):
        """
        Get department hardware item
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(hardware_item_id)
        hardware_items = departments_service.get_hardware_items_for_department(
            department_id
        )
        for hardware_item in hardware_items:
            if hardware_item["id"] == hardware_item_id:
                return hardware_item, 200
        raise HardwareItemNotFoundException

    @jwt_required()
    @permissions.require_admin
    @swag_from(SPECS["HardwareItemDepartmentResource_delete"])
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
    @swag_from(SPECS["DepartmentPersonsResource_get"])
    def get(self, department_id):
        """
        Get department members
        """
        self.check_id_parameter(department_id)
        # Who belongs to which department is how the studio is organized,
        # which present_client keeps from clients.
        permissions_service.block_access_to_client()
        persons = departments_service.get_persons_for_department(
            department_id, minimal=not permissions.has_admin_permissions()
        )
        return persons, 200
