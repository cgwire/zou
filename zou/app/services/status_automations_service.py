from zou.app.exceptions import (
    StatusAutomationNotFoundException,
    WrongParameterException,
)
from zou.app.models.project import ProjectStatusAutomationLink
from zou.app.models.project_template import (
    ProjectTemplateStatusAutomationLink,
)
from zou.app.models.status_automation import StatusAutomation
from zou.app.services import base_service
from zou.app.utils import cache, fields


def clear_status_automation_cache():
    """
    Drop the memoized status automation list.
    """
    cache.cache.delete_memoized(get_status_automations)


@cache.memoize_function(120)
def get_status_automations():
    """
    Return all status automations.
    """
    return fields.serialize_models(StatusAutomation.get_all())


def get_status_automation_raw(status_automation_id):
    """
    Get status automation matching given id as an active record.
    """
    return base_service.get_instance(
        StatusAutomation,
        status_automation_id,
        StatusAutomationNotFoundException,
    )


def guard_status_automation_deletion(status_automation_id):
    """
    Refuse the deletion of a status automation a project or a project
    template uses. Neither link table has a delete rule: the foreign key
    would refuse it with a raw database error.
    """
    if ProjectStatusAutomationLink.query.filter_by(
        status_automation_id=status_automation_id
    ).count():
        raise WrongParameterException("This automation is used in a project.")
    if ProjectTemplateStatusAutomationLink.query.filter_by(
        status_automation_id=status_automation_id
    ).count():
        raise WrongParameterException(
            "This automation is used in a project template."
        )


def get_automations_using_task_type(task_type_id):
    """
    Return the status automations, archived ones included, that read or
    write given task type. Read from the table, not from the memoized list:
    the answer guards a deletion.
    """
    task_type_id = str(task_type_id)
    return [
        automation.serialize()
        for automation in StatusAutomation.query.all()
        if task_type_id in _get_used_task_type_ids(automation)
    ]


def get_automations_using_task_status(task_status_id):
    """
    Return the status automations, archived ones included, that read or
    write given task status.
    """
    task_status_id = str(task_status_id)
    return [
        automation.serialize()
        for automation in StatusAutomation.query.all()
        if task_status_id in _get_used_task_status_ids(automation)
    ]


def guard_task_type_deletion(task_type):
    """
    Refuse the deletion of a task type a status automation uses. Dropping
    it from the automation would change when the automation fires, so the
    admin has to do it.
    """
    automations = get_automations_using_task_type(task_type["id"])
    if automations:
        raise WrongParameterException(
            _build_usage_message(f"Task type {task_type['name']}", automations)
        )


def guard_task_status_deletion(task_status):
    """
    Refuse the deletion of a task status a status automation uses.
    """
    automations = get_automations_using_task_status(task_status["id"])
    if automations:
        raise WrongParameterException(
            _build_usage_message(
                f"Task status {task_status['name']}", automations
            )
        )


def _get_used_task_type_ids(automation):
    return {
        str(task_type_id)
        for task_type_id in (
            automation.in_task_type_id,
            automation.out_task_type_id,
        )
        if task_type_id is not None
    }


def _get_used_task_status_ids(automation):
    return {
        str(task_status_id)
        for task_status_id in (
            automation.in_task_status_id,
            automation.out_task_status_id,
        )
        if task_status_id is not None
    }


def _build_usage_message(label, automations):
    count = len(automations)
    archived = len([a for a in automations if a["archived"]])
    noun = "status automation" if count == 1 else "status automations"
    detail = f" ({archived} archived)" if archived else ""
    them = "that automation" if count == 1 else "them"
    return (
        f"{label} is used by {count} {noun}{detail}. "
        f"Remove it from {them} first."
    )
