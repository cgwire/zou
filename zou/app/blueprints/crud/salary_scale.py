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
        Retrieve all salary scale entries.
        ---
        tags:
          - Crud
        description: Retrieve all salary scale entries.
        responses:
            200:
                description: All salary scale entries
            403:
                description: Permission denied
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
