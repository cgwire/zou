from zou.app import config
from zou.app.utils import events, cache, fields
from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.models.studio import Studio
from zou.app.exceptions import (
    TaskStatusNotFoundException,
    TaskTypeNotFoundException,
    WrongParameterException,
    StudioNotFoundException,
)
from zou.app.services import base_service


def clear_task_status_cache(task_status_id):
    """
    Drop the memoized serialization of given task status, and the list.
    """
    cache.cache.delete_memoized(get_task_status, task_status_id)
    cache.cache.delete_memoized(get_task_statuses)


def clear_task_type_cache(task_type_id):
    """
    Drop the memoized serializations of given task type, and the list.
    """
    cache.cache.delete_memoized(get_task_type, task_type_id)
    cache.cache.delete_memoized(get_task_types)


def clear_studio_cache(studio_id):
    """
    Drop the memoized serializations of given studio, and the list.
    """
    cache.cache.delete_memoized(get_studio, studio_id)
    cache.cache.delete_memoized(get_studios)


@cache.memoize_function(120)
def get_studios():
    """
    Return every studio.
    """
    return fields.serialize_models(Studio.get_all())


@cache.memoize_function(120)
def get_studio(studio_id):
    """
    Get studio matching given id as a dictionary.
    """
    return base_service.get_instance(
        Studio, studio_id, StudioNotFoundException
    ).serialize()


@cache.memoize_function(120)
def get_task_types():
    """
    Return every task type.
    """
    return fields.serialize_models(TaskType.get_all())


@cache.memoize_function(120)
def get_task_statuses():
    """
    Return every task status.
    """
    return fields.serialize_models(TaskStatus.get_all())


@cache.memoize_function(120)
def get_to_review_status():
    """
    Return the task status previews are set to on upload.
    """
    return get_or_create_task_status(config.TO_REVIEW_TASK_STATUS, "pndng")


@cache.memoize_function(120)
def get_default_task_status(for_concept=False):
    """
    Return the task status new tasks start on.
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


def get_task_status_raw(task_status_id):
    """
    Get task status matching given id as an active record.
    """
    return base_service.get_instance(
        TaskStatus, task_status_id, TaskStatusNotFoundException
    )


@cache.memoize_function(1200)
def get_task_status(task_status_id):
    """
    Get task status matching given id  as a dictionary.
    """
    return get_task_status_raw(task_status_id).serialize()


def get_task_status_map():
    """
    Return a dict of which keys are task status ids and values are task
    statuses.
    """
    return {
        str(status.id): status.serialize() for status in TaskStatus.query.all()
    }


def get_task_type_raw(task_type_id):
    """
    Get task type matching given id as an active record.
    """
    return base_service.get_instance(
        TaskType, task_type_id, TaskTypeNotFoundException
    )


@cache.memoize_function(1200)
def get_task_type(task_type_id):
    """
    Get task type matching given id as a dictionary.
    """
    return get_task_type_raw(task_type_id).serialize()


def get_task_type_map():
    """
    Return a dict of which keys are task type ids and values are task types.
    """
    task_types = TaskType.query.all()
    return {
        str(task_type.id): task_type.serialize() for task_type in task_types
    }


def check_task_type_name_is_unique(name, exclude_task_type_id=None):
    """
    Check that no task type carries given name, compared regardless of
    case: clients resolve a task type from its name and lower-case it on
    the way, so a twin differing only by case collapses onto the same
    entry. Raises WrongParameterException when one exists.

    The task type being renamed is excluded in the query rather than by
    comparing ids afterwards: a database can already hold such twins, and
    a lookup free to return any of them could hand back the renamed row
    and hide the conflict with the other.
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
    Create a new task status if it doesn't exist. If it exists, it returns the
    status from database.
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
    Create a new task type if it doesn't exist. If it exists, it returns the
    type from database. The name is matched regardless of case, so a
    bootstrap or an import never creates a twin the clients cannot tell
    apart (see check_task_type_name_is_unique).
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
