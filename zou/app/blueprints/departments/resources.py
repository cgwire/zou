from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.utils import permissions
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    departments_service,
)


class AllDepartmentSoftwareResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self):
        """
        Get all software items for all departments.
        ---
        tags:
        - Departments
        responses:
            200:
                description: A dictionary of departments with their software items
        """
        softwares = departments_service.get_all_software_for_departments()
        return softwares, 200


class AddSoftwareToDepartmentResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def post(self, department_id):
        """
        Add a software item to given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: software_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: User added to given department
            404:
                description: Department ID or Software ID matches no department or software
        """
        args = self.get_args(
            [
                ("software_id", None, True),
            ]
        )
        self.check_id_parameter(department_id)
        self.check_id_parameter(args["software_id"])
        software = departments_service.add_software_to_department(
            department_id, args["software_id"]
        )
        return software, 201


class SoftwareDepartmentResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self, department_id):
        """
        Get all software items for a given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Software items for given department
            404:
                description: Department ID matches no department
        """
        self.check_id_parameter(department_id)
        softwares = departments_service.get_softwares_for_department(
            department_id
        )
        return softwares, 200

    @jwt_required()
    @permissions.require_admin
    def delete(self, department_id, software_id):
        """
        Remove a software item from given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: software_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: User removed from given department
            404:
                description: Department or software ID matches no department or software
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(software_id)
        departments_service.remove_software_from_department(
            department_id, software_id
        )
        return "", 204


class AllDepartmentHardwareItemsResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self):
        """
        Get all hardware items for all departments.
        ---
        tags:
        - Departments
        responses:
            200:
                description: A dictionary of departments with their hardware items
        """
        hardware_items = (
            departments_service.get_all_hardware_items_for_departments()
        )
        return hardware_items, 200


class AddHardwareItemToDepartmentResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def post(self, department_id):
        """
        Add a hardware item to given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: hardware_item_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: Hardware item added to given department
            404:
                description: Department ID matches no department
            400:
                description: Hardware item ID matches no hardware item
        """
        args = self.get_args(
            [
                ("hardware_item_id", None, True),
            ]
        )
        self.check_id_parameter(department_id)
        self.check_id_parameter(args["hardware_item_id"])
        hardware_item_link = (
            departments_service.add_hardware_item_to_department(
                department_id, args["hardware_item_id"]
            )
        )
        return hardware_item_link, 201


class HardwareItemDepartmentResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def get(self, department_id):
        """
        Get all hardware items for a given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Hardware items for given department
            404:
                description: Department ID matches no department
        """
        self.check_id_parameter(department_id)
        hardware_items = departments_service.get_hardware_items_for_department(
            department_id
        )
        return hardware_items, 200

    @jwt_required()
    @permissions.require_admin
    def delete(self, department_id, hardware_item_id):
        """
        Remove a hardware item from given department.
        ---
        tags:
        - Departments
        parameters:
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: hardware_item_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: User removed from given department
            404:
                description: Department or software ID matches no department or software
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(hardware_item_id)
        departments_service.remove_hardware_item_from_department(
            department_id, hardware_item_id
        )
        return "", 204
