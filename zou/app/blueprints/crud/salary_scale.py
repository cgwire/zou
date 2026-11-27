from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.exceptions import WrongParameterException
from zou.app.models.salary_scale import SalaryScale
from zou.app.services import budget_service
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/salary_scale.yml")


class SalaryScalesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, SalaryScale)

    def check_creation_integrity(self, data):
        raise WrongParameterException("Salary scales cannot be created")

    @jwt_required()
    @swag_from(SPECS["SalaryScalesResource_get"])
    def get(self):
        """
        Get salary scales
        """
        self.check_read_permissions()
        query = self.model.query

        budget_service.create_missing_salary_scales()
        return self.all_entries(query)


class SalaryScaleResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, SalaryScale)
        # BaseModelResource.__init__ assigns protected_fields on the instance,
        # so a class attribute of the same name never applies: append after
        # it, else department_id is writable through a PUT.
        self.protected_fields.append("department_id")

    @jwt_required()
    @swag_from(SPECS["SalaryScaleResource_get"])
    def get(self, instance_id):
        """
        Get salary scale
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["SalaryScaleResource_put"])
    def put(self, instance_id):
        """
        Update salary scale
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["SalaryScaleResource_delete"])
    def delete(self, instance_id):
        """
        Delete salary scale
        """
        return super().delete(instance_id)
