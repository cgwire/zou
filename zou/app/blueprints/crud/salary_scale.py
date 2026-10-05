from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.exceptions import WrongParameterException

from zou.app.models.department import Department
from zou.app.models.salary_scale import SalaryScale


from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES


class SalaryScalesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SalaryScale)

    def check_creation_integrity(self, data):
        raise WrongParameterException("Salary scales cannot be created")

    @jwt_required()
    @swag_from("openapi/SalaryScalesResource_get.yml")
    def get(self):
        """
        Get salary scales
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
    def __init__(self):
        BaseModelResource.__init__(self, SalaryScale)
        # BaseModelResource.__init__ assigns protected_fields on the instance,
        # so the class attribute this used to declare never applied and
        # department_id was writable through a PUT.
        self.protected_fields.append("department_id")

    @jwt_required()
    @swag_from("openapi/SalaryScaleResource_get.yml")
    def get(self, instance_id):
        """
        Get salary scale
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/SalaryScaleResource_put.yml")
    def put(self, instance_id):
        """
        Update salary scale
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/SalaryScaleResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete salary scale
        """
        return super().delete(instance_id)
