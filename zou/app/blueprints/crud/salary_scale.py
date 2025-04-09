from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.services.exception import WrongParameterException

from zou.app.models.department import Department
from zou.app.models.salary_scale import SalaryScale



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

        departments = Department.query.all()
        salary_scales = SalaryScale.query.all()
        salary_scale_map = {
            str(salary_scale.department_id): True
            for salary_scale in salary_scales
        }
        for department in departments:
            if str(department.id) not in salary_scale_map:
                SalaryScale.create(department_id=department.id)

        return self.all_entries(query)


class SalaryScaleResource(BaseModelResource):
    protected_fields = ["id", "created_at", "updated_at", "department_id"]

    def __init__(self):
        BaseModelResource.__init__(self, SalaryScale)
