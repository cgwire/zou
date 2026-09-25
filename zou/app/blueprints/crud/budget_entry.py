from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.budget_entry import BudgetEntry


class BudgetEntriesResource(BaseModelsResource):

    def __init__(self):
        BaseModelsResource.__init__(self, BudgetEntry)

    @jwt_required()
    @swag_from("openapi/BudgetEntriesResource_get.yml")
    def get(self):
        """
        Get budget entries
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/BudgetEntriesResource_post.yml")
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
    @swag_from("openapi/BudgetEntryResource_get.yml")
    def get(self, instance_id):
        """
        Get budget entry
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/BudgetEntryResource_put.yml")
    def put(self, instance_id):
        """
        Update budget entry
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/BudgetEntryResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete budget entry
        """
        return super().delete(instance_id)
