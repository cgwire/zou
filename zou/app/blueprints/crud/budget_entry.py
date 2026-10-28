from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelResource, BaseModelsResource
from zou.app.models.budget_entry import BudgetEntry
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/budget_entry.yml")


class BudgetEntriesResource(BaseModelsResource):

    def __init__(self):
        BaseModelsResource.__init__(self, BudgetEntry)

    @jwt_required()
    @swag_from(SPECS["BudgetEntriesResource_get"])
    def get(self):
        """
        Get budget entries
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["BudgetEntriesResource_post"])
    def post(self):
        """
        Create budget entry
        """
        return super().post()


class BudgetEntryResource(BaseModelResource):

    def __init__(self):
        BaseModelResource.__init__(self, BudgetEntry)
        # BudgetEntry has no project_id, so the base class protects nothing
        # here: budget_id is what ties the entry to a production.
        self.protected_fields.append("budget_id")

    @jwt_required()
    @swag_from(SPECS["BudgetEntryResource_get"])
    def get(self, instance_id):
        """
        Get budget entry
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["BudgetEntryResource_put"])
    def put(self, instance_id):
        """
        Update budget entry
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from(SPECS["BudgetEntryResource_delete"])
    def delete(self, instance_id):
        """
        Delete budget entry
        """
        return super().delete(instance_id)
