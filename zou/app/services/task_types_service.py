from zou.app import config
from zou.app.exceptions import (
    StudioNotFoundException,
    TaskStatusNotFoundException,
    TaskTypeNotFoundException,
    WrongParameterException,
)
from zou.app.models.department import Department
from zou.app.models.studio import Studio
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import base_service
from zou.app.utils import cache, events, fields


def clear_task_status_cache(task_status_id):
    """
    Drop the memoized serialization of the given task status and the list.
    Also drop the default and to-review lookups, because the status can
    now be one of them.
    """
    cache.cache.delete_memoized(get_task_status, task_status_id)
    cache.cache.delete_memoized(get_task_statuses)
    cache.cache.delete_memoized(get_default_task_status)
    cache.cache.delete_memoized(get_to_review_status)


def clear_task_type_cache(task_type_id):
    """
    Drop the memoized serializations of the given task type and the list.
    """
    cache.cache.delete_memoized(get_task_type, task_type_id)
    cache.cache.delete_memoized(get_task_types)


def clear_studio_cache(studio_id):
    """
    Drop the memoized serializations of the given studio and the list.
    """
    cache.cache.delete_memoized(get_studio, studio_id)
    cache.cache.delete_memoized(get_studios)


@cache.memoize_function(120)
def get_studios():
    """
    Return all the studios.
    """
    return fields.serialize_models(Studio.get_all())


@cache.memoize_function(120)
def get_studio(studio_id):
    """
    Return the studio that has the given ID, as a dict.
    """
    return base_service.get_instance(
        Studio, studio_id, StudioNotFoundException
    ).serialize()


@cache.memoize_function(120)
def get_task_types():
    """
    Return all the task types.
    """
    return fields.serialize_models(TaskType.get_all())


def get_task_types_with_department_names_query():
    """
    Return a query on the task types joined with the name of their
    department, sorted by department name and task type name.
    """
    query = TaskType.query.order_by(Department.name, TaskType.name)
    query = query.join(Department, TaskType.department_id == Department.id)
    return query.add_columns(Department.name)


@cache.memoize_function(120)
def get_task_statuses():
    """
    Return all the task statuses.
    """
    return fields.serialize_models(TaskStatus.get_all())


@cache.memoize_function(120)
def get_to_review_status():
    """
    Return the task status that a preview upload sets.
    """
    return get_or_create_task_status(config.TO_REVIEW_TASK_STATUS, "pndng")


@cache.memoize_function(120)
def get_default_task_status(for_concept=False):
    """
    Return the task status that new tasks start with.
    """
    if for_concept:
        return get_or_create_task_status(
            "Neutral",
            "neutral",
            "#CCCCCC",
            is_default=True,
            for_concept=True,
        )
    else:
        return get_or_create_task_status(
            "Todo", "todo", "#f5f5f5", is_default=True
        )


def unset_default_task_status_no_commit(for_concept, task_status_id=None):
    """
    Set is_default=False on the default task status of the given kind
    (concept or task), except the status that has the given ID. This
    function does not commit: the caller commits it with the write that
    sets the new default, so a failed write keeps the old default. Return
    the IDs of the statuses that are not the default anymore.
    """
    query = TaskStatus.query.filter(
        TaskStatus.is_default == True,
        TaskStatus.for_concept == bool(for_concept),
    )
    if task_status_id is not None:
        query = query.filter(TaskStatus.id != task_status_id)
    unset_ids = [str(row[0]) for row in query.with_entities(TaskStatus.id)]
    query.update({"is_default": False})
    return unset_ids


def get_task_status_raw(task_status_id):
    """
    Return the task status that has the given ID, as an active record.
    """
    return base_service.get_instance(
        TaskStatus, task_status_id, TaskStatusNotFoundException
    )


@cache.memoize_function(1200)
def get_task_status(task_status_id):
    """
    Return the task status that has the given ID, as a dict.
    """
    return get_task_status_raw(task_status_id).serialize()


def get_task_status_map():
    """
    Return a dict with task status IDs as keys and task statuses as values.
    """
    return {
        str(status.id): status.serialize() for status in TaskStatus.query.all()
    }


def get_task_type_raw(task_type_id):
    """
    Return the task type that has the given ID, as an active record.
    """
    return base_service.get_instance(
        TaskType, task_type_id, TaskTypeNotFoundException
    )


@cache.memoize_function(1200)
def get_task_type(task_type_id):
    """
    Return the task type that has the given ID, as a dict.
    """
    return get_task_type_raw(task_type_id).serialize()


def get_task_type_map():
    """
    Return a dict with task type IDs as keys and task types as values.
    """
    task_types = TaskType.query.all()
    return {
        str(task_type.id): task_type.serialize() for task_type in task_types
    }


def check_task_type_name_is_unique(name, exclude_task_type_id=None):
    """
    Make sure that no task type has the given name. The comparison ignores
    the case. Clients find a task type from its name and change the name to
    lower case. Because of this, two names that differ only by the case
    point to the same entry. If such a task type exists, raise
    WrongParameterException.

    The query excludes the task type that changes its name. A comparison of
    the IDs after the query is not enough: a database can already hold
    such twins. A query that can return any of them can return the renamed
    row and hide the conflict with the other row.
    """
    criterions = []
    if exclude_task_type_id is not None:
        criterions.append(TaskType.id != exclude_task_type_id)
    if TaskType.get_by_case_insensitive(*criterions, name=name) is not None:
        raise WrongParameterException(
            "A task type with similar name already exists"
        )


def get_or_create_task_status(
    name,
    short_name="",
    color="#f5f5f5",
    is_done=False,
    is_retake=False,
    is_feedback_request=False,
    is_default=False,
    is_wip=False,
    for_concept=False,
    is_artist_allowed=True,
    is_client_allowed=True,
):
    """
    Create a new task status if it does not exist. If it exists, return the
    status from the database.
    """
    if is_default:
        task_status = TaskStatus.get_by(
            is_default=is_default, for_concept=for_concept
        )
    else:
        task_status = TaskStatus.get_by(name=name, for_concept=for_concept)
    if task_status is None and len(short_name) > 0:
        task_status = TaskStatus.get_by(
            short_name=short_name, for_concept=for_concept
        )

    if task_status is None:
        task_status = TaskStatus.create(
            name=name,
            short_name=short_name or name.lower(),
            color=color,
            is_done=is_done,
            is_retake=is_retake,
            is_feedback_request=is_feedback_request,
            is_default=is_default,
            for_concept=for_concept,
            is_artist_allowed=is_artist_allowed,
            is_client_allowed=is_client_allowed,
            is_wip=is_wip,
        )
        clear_task_status_cache(str(task_status.id))
        events.emit("task-status:new", {"task_status_id": task_status.id})
    return task_status.serialize()


def get_or_create_task_type(
    department,
    name,
    color="#888888",
    priority=1,
    for_entity="Asset",
    short_name="",
    shotgun_id=None,
):
    """
    Create a new task type if it does not exist. If it exists, return the
    type from the database. The name comparison ignores the case. Because
    of this, a bootstrap or an import never creates a twin that the clients
    see as the same task type (see check_task_type_name_is_unique).
    """
    task_type = TaskType.get_by_case_insensitive(
        name=name, for_entity=for_entity
    )
    if task_type is None:
        task_type = TaskType.create(
            name=name,
            short_name=short_name,
            department_id=department["id"],
            color=color,
            priority=priority,
            for_entity=for_entity,
            shotgun_id=shotgun_id,
        )
        events.emit("task-type:new", {"task_type_id": task_type.id})
        clear_task_type_cache(str(task_type.id))
    return task_type.serialize()
