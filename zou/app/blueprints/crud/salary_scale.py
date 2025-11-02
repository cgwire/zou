from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services.exception import WrongParameterException

from zou.app.models.department import Department
from zou.app.models.salary_scale import SalaryScale


from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES


class SalaryScalesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SalaryScale)

    def check_creation_integrity(self, data):
        raise WrongParameterException("Salary scales cannot be created")

    @jwt_required()
    def get(self):
        """
        Get salary scales
        ---
        tags:
          - Crud
        description: Retrieve all salary scale entries. Automatically
          creates missing combinations of department, position, and
          seniority.
        responses:
            200:
              description: Salary scales retrieved successfully
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
                          example: a24a6ea4-ce75-4665-a070-57453082c25
                        department_id:
                          type: string
                          format: uuid
                          example: b24a6ea4-ce75-4665-a070-57453082c25
                        position:
                          type: string
                          example: artist
                        seniority:
                          type: string
                          example: junior
                        rate:
                          type: number
                          example: 50.0
            400:
              description: Query error
        """
        self.check_read_permissions()
        query = self.model.query

        position_types = [position for position, _ in POSITION_TYPES]
        seniority_types = [seniority for seniority, _ in SENIORITY_TYPES]

        departments = Department.query.all()
        salary_scales = SalaryScale.query.all()
        salary_scale_map = {}
        for salary_scale in salary_scales:
            key = (
                f"{salary_scale.department_id}-"
                + f"{salary_scale.position.value.lower()}-"
                + f"{salary_scale.seniority.value.lower()}"
            )
            salary_scale_map[key] = True

        for department in departments:
            for position in position_types:
                for seniority in seniority_types:
                    key = (
                        f"{department.id}-"
                        + f"{position.lower()}-"
                        + f"{seniority.lower()}"
                    )
                    if key not in salary_scale_map:
                        SalaryScale.create(
                            department_id=department.id,
                            position=position,
                            seniority=seniority,
                        )
        return self.all_entries(query)


class SalaryScaleResource(BaseModelResource):
    protected_fields = ["id", "created_at", "updated_at", "department_id"]

    def __init__(self):
        BaseModelResource.__init__(self, SalaryScale)

    @jwt_required()
    def get(self, instance_id):
        """
        Get salary scale
        ---
        tags:
          - Crud
        description: Retrieve a salary scale by its ID and return it as
          a JSON object. Supports including relations.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Salary scale retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      department_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      position:
                        type: string
                        example: artist
                      seniority:
                        type: string
                        example: junior
                      rate:
                        type: number
                        example: 50.0
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        return super().get(instance_id)

    @jwt_required()
    def put(self, instance_id):
        """
        Update salary scale
        ---
        tags:
          - Crud
        description: Update a salary scale with data provided in the
          request body. JSON format is expected. Department ID cannot
          be changed.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  rate:
                    type: number
                    example: 55.0
        responses:
            200:
              description: Salary scale updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      department_id:
                        type: string
                        format: uuid
                        example: b24a6ea4-ce75-4665-a070-57453082c25
                      position:
                        type: string
                        example: artist
                      seniority:
                        type: string
                        example: junior
                      rate:
                        type: number
                        example: 55.0
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
        """
        return super().put(instance_id)

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete salary scale
        ---
        tags:
          - Crud
        description: Delete a salary scale by its ID. Returns empty
          response on success.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Salary scale deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        return super().delete(instance_id)
