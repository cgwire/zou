from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry

from zou.app.services import base_service
from zou.app.services.exception import (
    BudgetNotFoundException,
    BudgetEntryNotFoundException,
)

from zou.app.utils import events
from zou.app.utils import fields


def _clean_exceptions(data):
    """
    Normalize the exception map of a budget entry: a missing map becomes an
    empty one, and months set to zero or to null are dropped rather than
    stored.
    """
    if "exceptions" in data:
        if data["exceptions"] is None:
            data["exceptions"] = {}
        else:
            data["exceptions"] = {
                k: int(v)
                for k, v in data["exceptions"].items()
                if v is not None and int(v) > 0
            }
    return data


def get_budget_raw(budget_id):
    """
    Return budget corresponding to given budget ID.
    """
    return base_service.get_instance(
        Budget, budget_id, BudgetNotFoundException
    )


def get_budget(budget_id):
    """
    Return budget corresponding to given budget ID as a dictionary.
    """
    return get_budget_raw(budget_id).serialize(relations=True)


def get_budgets(project_id):
    """
    Return all budgets for given project ID.
    """
    budgets = Budget.get_all_by(project_id=project_id)
    return fields.present_models(budgets)


def create_budget(project_id, name, currency=None):
    """
    Create a new budget for given project ID.
    """
    last_budget = (
        Budget.query.filter_by(project_id=project_id)
        .order_by(Budget.revision.desc())
        .first()
    )
    revision = 1 if last_budget is None else last_budget.revision + 1
    budget = Budget(
        project_id=project_id,
        name=name,
        currency=currency,
        revision=revision,
    )
    budget.save()
    events.emit(
        "budget:create",
        {"budget_id": str(budget.id)},
        project_id=project_id,
    )
    return budget.serialize()


def update_budget(budget_id, name=None, currency=None):
    """
    Update budget corresponding to given budget ID.
    """
    budget = get_budget_raw(budget_id)
    if name is not None:
        budget.name = name
    if currency is not None:
        budget.currency = currency
    budget.save()
    events.emit(
        "budget:update",
        {"budget_id": str(budget.id)},
        project_id=str(budget.project_id),
    )
    return budget.serialize()


def delete_budget(budget_id):
    """
    Delete budget corresponding to given budget ID.
    """
    budget = get_budget_raw(budget_id)
    BudgetEntry.delete_all_by(budget_id=budget_id)
    budget.delete()
    events.emit(
        "budget:delete",
        {"budget_id": budget_id},
        project_id=str(budget.project_id),
    )
    return budget.serialize()


def get_budget_entries(budget_id):
    """
    Return all budget entries for given budget ID.
    """
    budget_entries = BudgetEntry.get_all_by(budget_id=budget_id)
    return fields.present_models(budget_entries)


def get_budget_entry_raw(budget_entry_id):
    """
    Return budget entry corresponding to given budget entry ID.
    """
    return base_service.get_instance(
        BudgetEntry, budget_entry_id, BudgetEntryNotFoundException
    )


def get_budget_entry(budget_entry_id):
    """
    Return budget entry corresponding to given budget entry ID as a dictionary.
    """
    return get_budget_entry_raw(budget_entry_id).serialize()


def create_budget_entry(
    budget_id,
    department_id,
    start_date,
    months_duration,
    daily_salary,
    position,
    seniority,
    person_id=None,
):
    """
    Create a new budget entry for given budget ID.
    """
    budget = get_budget_raw(budget_id)
    budget_entry = BudgetEntry.create(
        budget_id=budget_id,
        department_id=department_id,
        person_id=person_id,
        start_date=start_date,
        months_duration=months_duration,
        daily_salary=daily_salary,
        position=position,
        seniority=seniority,
        exceptions={},
    )
    events.emit(
        "budget-entry:create",
        {"budget_id": str(budget_id), "budget_entry_id": str(budget_entry.id)},
        project_id=str(budget.project_id),
    )
    return budget_entry.serialize()


def update_budget_entry(budget_entry_id, data):
    """
    Update budget entry corresponding to given budget entry ID.
    """
    budget_entry = get_budget_entry_raw(budget_entry_id)
    budget = get_budget_raw(str(budget_entry.budget_id))
    data = _clean_exceptions(data)
    budget_entry.update(data)
    events.emit(
        "budget-entry:update",
        {"budget_id": str(budget.id), "budget_entry_id": str(budget_entry.id)},
        project_id=str(budget.project_id),
    )
    return budget_entry.serialize()


def delete_budget_entry(budget_entry_id):
    """
    Delete budget entry corresponding to given budget entry ID.
    """
    budget_entry = get_budget_entry_raw(budget_entry_id)
    budget = get_budget_raw(str(budget_entry.budget_id))
    budget_entry.delete()
    events.emit(
        "budget-entry:delete",
        {"budget_id": str(budget.id), "budget_entry_id": budget_entry_id},
        project_id=str(budget.project_id),
    )
    return budget_entry.serialize()
