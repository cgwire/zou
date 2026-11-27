from zou.app.exceptions import (
    BudgetEntryNotFoundException,
    BudgetNotFoundException,
)
from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.models.department import Department
from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES
from zou.app.models.salary_scale import SalaryScale
from zou.app.services import base_service
from zou.app.utils import events, fields


def _clean_exceptions(data):
    """
    Normalize the exception map of a budget entry. If the map is null, use an
    empty map. Remove the months that have a null, zero or negative value: do
    not store them.
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


def create_missing_salary_scales():
    """
    Create a salary scale for each combination of department, position and
    seniority that has no salary scale.
    """
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


def get_budget_raw(budget_id):
    """
    Return the budget that has the given budget ID.
    """
    return base_service.get_instance(
        Budget, budget_id, BudgetNotFoundException
    )


def get_budget(budget_id, project_id=None):
    """
    Return the budget that has the given budget ID as a dict. If a project ID
    is given, a budget of another project is not found.
    """
    budget = get_budget_raw(budget_id).serialize(relations=True)
    if project_id is not None and budget["project_id"] != str(project_id):
        raise BudgetNotFoundException
    return budget


def get_budgets(project_id):
    """
    Return all budgets for the given project ID.
    """
    budgets = Budget.get_all_by(project_id=project_id)
    return fields.present_models(budgets)


def create_budget(project_id, name, currency=None):
    """
    Create a budget for the given project ID. Its revision is the last
    revision of the project budgets plus one.
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
    Update the budget that has the given budget ID.
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
    Delete the budget that has the given budget ID and all its entries.
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
    Return all budget entries for the given budget ID.
    """
    budget_entries = BudgetEntry.get_all_by(budget_id=budget_id)
    return fields.present_models(budget_entries)


def get_budget_entry_raw(budget_entry_id):
    """
    Return the budget entry that has the given budget entry ID.
    """
    return base_service.get_instance(
        BudgetEntry, budget_entry_id, BudgetEntryNotFoundException
    )


def get_budget_entry(budget_entry_id, budget_id=None):
    """
    Return the budget entry that has the given budget entry ID as a dict. If
    a budget ID is given, an entry of another budget is not found.
    """
    entry = get_budget_entry_raw(budget_entry_id).serialize()
    if budget_id is not None and entry["budget_id"] != str(budget_id):
        raise BudgetEntryNotFoundException
    return entry


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
    Create a budget entry for the given budget ID.
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
    Update the budget entry that has the given budget entry ID.
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
    Delete the budget entry that has the given budget entry ID.
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
