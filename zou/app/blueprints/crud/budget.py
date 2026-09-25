from flasgger import swag_from
from flask_jwt_extended import jwt_required

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.budget import Budget


class BudgetsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Budget)

    @jwt_required()
    @swag_from("openapi/BudgetsResource_get.yml")
    def get(self):
        """
        Get budgets
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/BudgetsResource_post.yml")
    def post(self):
        """
        Create budget
        """
        return super().post()


class BudgetResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Budget)
        # BaseModelResource.__init__ assigns protected_fields on the instance,
        # so a class attribute of the same name never applies: append after it.
        # project_id is already added there, revision identifies the quote.
        self.protected_fields.append("revision")

    @jwt_required()
    @swag_from("openapi/BudgetResource_get.yml")
    def get(self, instance_id):
        """
        Get budget
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/BudgetResource_put.yml")
    def put(self, instance_id):
        """
        Update budget
        """
        return super().put(instance_id)

    @jwt_required()
    @swag_from("openapi/BudgetResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete budget
        """
        return super().delete(instance_id)
