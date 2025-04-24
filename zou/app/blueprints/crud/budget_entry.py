from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.salary_scale import BudgetEntry


class BudgetEntriesResource(BaseModelsResource):

    def __init__(self):
        BaseModelsResource.__init__(self, BudgetEntry)


class BudgetEntryResource(BaseModelResource):

    def __init__(self):
        BaseModelResource.__init__(self, BudgetEntry)
