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
        Get all department software licenses
        ---
        description: Retrieve all software licenses organized by department.
          Returns a dictionary where each department contains its associated
          software licenses.
        tags:
          - Departments
        responses:
          200:
            description: Department software licenses successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          description: Software license unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Software license name
                          example: "Maya"
                        short_name:
                          type: string
                          description: Software license short name
                          example: "MAYA"
                        file_extension:
                          type: string
                          description: Default file extension for the software license
                          example: ".ma"
                        department_id:
                          type: string
                          format: uuid
                          description: Department identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        created_at:
                          type: string
                          format: date-time
                          description: Creation timestamp
                          example: "2023-01-01T12:00:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          description: Last update timestamp
                          example: "2023-01-01T12:30:00Z"
        """
        softwares = departments_service.get_all_software_for_departments()
        return softwares, 200


class AddSoftwareToDepartmentResource(Resource, ArgsMixin):

    @jwt_required()
    @permissions.require_admin
    def post(self, department_id):
        """
        Add software license to department
        ---
        description: Associate a software license with a specific department.
          This allows the department to use the specified software in budget
          forecasting.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - software_id
                properties:
                  software_id:
                    type: string
                    format: uuid
                    description: Software identifier to add to department
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Software license successfully added to department
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Software license department link unique identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    department_id:
                      type: string
                      format: uuid
                      description: Department identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    software_id:
                      type: string
                      format: uuid
                      description: Software license identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
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
        Get department software licenses
        ---
        description: Retrieve all software items that are associated with a
          specific department.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
        responses:
          200:
            description: Department software licenses successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Software license unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Software license name
                        example: "Maya"
                      short_name:
                        type: string
                        description: Software license short name
                        example: "MAYA"
                      file_extension:
                        type: string
                        description: Default file extension for the software license
                        example: ".ma"
                      department_id:
                        type: string
                        format: uuid
                        description: Department identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Remove software license from department
        ---
        description: Remove a software license from a specific department.
          This disassociates the software license from the department.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
          - in: path
            name: software_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the software license to remove
        responses:
          204:
            description: Software license successfully removed from department
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
        Get all department hardware items
        ---
        description: Retrieve all hardware items organized by department.
          Returns a dictionary where each department contains its associated
          hardware items.
        tags:
          - Departments
        responses:
          200:
            description: Department hardware items successfully retrieved
            content:
              application/json:
                schema:
                  type: object
                  additionalProperties:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          format: uuid
                          description: Hardware item unique identifier
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        name:
                          type: string
                          description: Hardware item name
                          example: "Workstation"
                        description:
                          type: string
                          description: Hardware item description
                          example: "High-performance workstation"
                        department_id:
                          type: string
                          format: uuid
                          description: Department identifier
                          example: b35b7fb5-df86-5776-b181-68564193d36
                        created_at:
                          type: string
                          format: date-time
                          description: Creation timestamp
                          example: "2023-01-01T12:00:00Z"
                        updated_at:
                          type: string
                          format: date-time
                          description: Last update timestamp
                          example: "2023-01-01T12:30:00Z"
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
        Add hardware item to department
        ---
        description: Associate a hardware item with a specific department.
          This allows the department to use the specified hardware in budget
          forecasting.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - hardware_item_id
                properties:
                  hardware_item_id:
                    type: string
                    format: uuid
                    description: Hardware item identifier to add to department
                    example: b35b7fb5-df86-5776-b181-68564193d36
        responses:
          201:
            description: Hardware item successfully added to department
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Hardware department link unique identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    department_id:
                      type: string
                      format: uuid
                      description: Department identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    hardware_item_id:
                      type: string
                      format: uuid
                      description: Hardware item identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
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
        Get department hardware items
        ---
        description: Retrieve all hardware items that are associated with a
          specific department.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
        responses:
          200:
            description: Department hardware items successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Hardware item unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Hardware item name
                        example: "Workstation"
                      description:
                        type: string
                        description: Hardware item description
                        example: "High-performance workstation"
                      department_id:
                        type: string
                        format: uuid
                        description: Department identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        description: Last update timestamp
                        example: "2023-01-01T12:30:00Z"
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
        Remove hardware item from department
        ---
        description: Remove a hardware item from a specific department.
          This disassociates the hardware from the department.
        tags:
          - Departments
        parameters:
          - in: path
            name: department_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the department
          - in: path
            name: hardware_item_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the hardware item to remove
        responses:
          204:
            description: Hardware item successfully removed from department
        """
        self.check_id_parameter(department_id)
        self.check_id_parameter(hardware_item_id)
        departments_service.remove_hardware_item_from_department(
            department_id, hardware_item_id
        )
        return "", 204
