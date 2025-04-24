from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.salary_scale import Budget


class BudgetsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Budget)


class BudgetResource(BaseModelResource):
    protected_fields = [
        "id",
        "created_at",
        "updated_at",
        "project_id",
        "revision",
    ]

    def __init__(self):
        BaseModelResource.__init__(self, Budget)
