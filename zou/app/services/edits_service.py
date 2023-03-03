from sqlalchemy.orm import aliased
from sqlalchemy.exc import StatementError

from zou.app.utils import (
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app.models.entity import Entity, EntityLink, EntityVersion
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task
from zou.app.models.task import assignees_table

from zou.app.services import (
    deletion_service,
    entities_service,
    notifications_service,
    user_service,
)
from zou.app.services.exception import (
    EditNotFoundException,
    WrongIdFormatException,
)


def clear_edit_cache(edit_id):
    cache.cache.delete_memoized(get_edit, edit_id)
    cache.cache.delete_memoized(get_edit_with_relations, edit_id)
    cache.cache.delete_memoized(get_full_edit, edit_id)


@cache.memoize_function(1200)
def get_edit_type():
    return entities_service.get_temporal_entity_type_by_name("Edit")


def get_edits(criterions={}):
    """
    Get all edits for given criterions.
    """
    edit_type = get_edit_type()
    criterions["entity_type_id"] = edit_type["id"]
    is_only_assignation = "assigned_to" in criterions
    if is_only_assignation:
        del criterions["assigned_to"]

    query = Entity.query
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    query = query.join(Project).add_columns(Project.name).order_by(Entity.name)

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(user_service.build_assignee_filter())

    try:
        data = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException

    edits = []
    for edit_model, project_name in data:
        edit = edit_model.serialize(obj_type="Edit")
        edit["project_name"] = project_name
        edits.append(edit)

    return edits


def get_edits_and_tasks(criterions={}):
    """
    Get all edits for given criterions with related tasks for each edit.
    """
    edit_type = get_edit_type()
    edit_map = {}
    task_map = {}
    Episode = aliased(Entity, name="episode")
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), get_edit_type()["id"]
    )

    query = (
        Entity.query.join(Project, Entity.project_id == Project.id)
        .outerjoin(Episode, Episode.id == Entity.parent_id)
        .outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(assignees_table)
        .add_columns(
            Episode.id,
            Episode.name,
            Task.id,
            Task.task_type_id,
            Task.task_status_id,
            Task.priority,
            Task.estimation,
            Task.duration,
            Task.retake_count,
            Task.real_start_date,
            Task.end_date,
            Task.start_date,
            Task.due_date,
            Task.last_comment_date,
            Task.nb_assets_ready,
            assignees_table.columns.person,
            Project.id,
            Project.name,
        )
        .filter(Entity.entity_type_id == edit_type["id"])
    )
    if "id" in criterions:
        query = query.filter(Entity.id == criterions["id"])

    if "project_id" in criterions:
        query = query.filter(Entity.project_id == criterions["project_id"])

    if "episode_id" in criterions:
        query = query.filter(Entity.parent_id == criterions["episode_id"])

    if "assigned_to" in criterions:
        query = query.filter(user_service.build_assignee_filter())
        del criterions["assigned_to"]

    query_result = query.all()

    if "vendor_departments" in criterions:
        not_allowed_descriptors_field_names = (
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                "Edit",
                criterions["vendor_departments"],
                set(edit[0].project_id for edit in query_result),
            )
        )

    for (
        edit,
        episode_id,
        episode_name,
        task_id,
        task_type_id,
        task_status_id,
        task_priority,
        task_estimation,
        task_duration,
        task_retake_count,
        task_real_start_date,
        task_end_date,
        task_start_date,
        task_due_date,
        task_last_comment_date,
        task_nb_assets_ready,
        person_id,
        project_id,
        project_name,
    ) in query.all():
        edit_id = str(edit.id)

        if edit_id not in edit_map:
            data = fields.serialize_value(edit.data or {})
            if "vendor_departments" in criterions:
                data = (
                    entities_service.remove_not_allowed_fields_from_metadata(
                        not_allowed_descriptors_field_names[edit.project_id],
                        data,
                    )
                )

            edit_map[edit_id] = fields.serialize_dict(
                {
                    "canceled": edit.canceled,
                    "data": data,
                    "description": edit.description,
                    "entity_type_id": edit.entity_type_id,
                    "episode_id": episode_id,
                    "episode_name": episode_name or "",
                    "id": edit.id,
                    "name": edit.name,
                    "parent_id": edit.parent_id,
                    "preview_file_id": edit.preview_file_id or None,
                    "project_id": project_id,
                    "project_name": project_name,
                    "source_id": edit.source_id,
                    "nb_entities_out": edit.nb_entities_out,
                    "tasks": [],
                    "type": "Edit",
                }
            )

        if task_id is not None:
            task_id = str(task_id)
            if task_id not in task_map:
                task_dict = fields.serialize_dict(
                    {
                        "id": task_id,
                        "duration": task_duration,
                        "due_date": task_due_date,
                        "entity_id": edit_id,
                        "end_date": task_end_date,
                        "estimation": task_estimation,
                        "last_comment_date": task_last_comment_date,
                        "is_subscribed": subscription_map.get(task_id, False),
                        "nb_assets_ready": task_nb_assets_ready,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "task_status_id": task_status_id,
                        "task_type_id": task_type_id,
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                edit_dict = edit_map[edit_id]
                edit_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(edit_map.values())


def get_edit_raw(edit_id):
    """
    Return given edit as an active record.
    """
    edit_type = get_edit_type()
    try:
        edit = Entity.get_by(entity_type_id=edit_type["id"], id=edit_id)
    except StatementError:
        raise EditNotFoundException

    if edit is None:
        raise EditNotFoundException

    return edit


@cache.memoize_function(120)
def get_edit(edit_id):
    """
    Return given edit as a dictionary.
    """
    return get_edit_raw(edit_id).serialize(obj_type="Edit")


@cache.memoize_function(120)
def get_edit_with_relations(edit_id):
    """
    Return given edit as a dictionary.
    """
    return get_edit_raw(edit_id).serialize(obj_type="Edit", relations=True)


@cache.memoize_function(120)
def get_full_edit(edit_id):
    """
    Return given edit as a dictionary with extra data like project.
    """
    edits = get_edits_and_tasks({"id": edit_id})
    if len(edits) > 0:
        return edits[0]
    else:
        raise EditNotFoundException


def is_edit(entity):
    """
    Returns True if given entity has 'Edit' as entity type
    """
    edit_type = get_edit_type()
    return str(entity["entity_type_id"]) == edit_type["id"]


def get_edits_for_project(project_id, only_assigned=False):
    """
    Retrieve all edits related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id, get_edit_type()["id"], "Edit", only_assigned=only_assigned
    )


def get_edits_for_episode(episode_id, relations=False):
    """
    Get all edits for given episode.
    """
    edit_type_id = get_edit_type()["id"]
    result = (
        Entity.query.filter(Entity.entity_type_id == edit_type_id).filter(
            Entity.parent_id == episode_id
        )
    ).all()
    return Entity.serialize_list(result, "Edit", relations=relations)


def remove_edit(edit_id, force=False):
    """
    Remove given edit from database. If it has tasks linked to it, it marks
    the edit as canceled. Deletion can be forced.
    """
    edit = get_edit_raw(edit_id)
    is_tasks_related = Task.query.filter_by(entity_id=edit_id).count() > 0

    if is_tasks_related and not force:
        edit.update({"canceled": True})
        clear_edit_cache(edit_id)
        events.emit(
            "edit:update",
            {"edit_id": edit_id},
            project_id=str(edit.project_id),
        )
    else:
        from zou.app.services import tasks_service

        tasks = Task.query.filter_by(entity_id=edit_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))

        EntityVersion.delete_all_by(entity_id=edit_id)
        Subscription.delete_all_by(entity_id=edit_id)
        EntityLink.delete_all_by(entity_in_id=edit_id)
        edit.delete()
        clear_edit_cache(edit_id)
        events.emit(
            "edit:delete",
            {"edit_id": edit_id},
            project_id=str(edit.project_id),
        )

    deleted_edit = edit.serialize(obj_type="Edit")
    return deleted_edit


def create_edit(project_id, name, data={}, description="", parent_id=None):
    """
    Create edit for given project and episode.
    """
    edit_type = get_edit_type()

    if parent_id is not None and len(parent_id) < 36:
        parent_id = None

    edit = Entity.get_by(
        entity_type_id=edit_type["id"],
        parent_id=parent_id,
        project_id=project_id,
        name=name,
    )
    if edit is None:
        edit = Entity.create(
            entity_type_id=edit_type["id"],
            project_id=project_id,
            parent_id=parent_id,
            name=name,
            data=data,
            description=description,
        )
    events.emit(
        "edit:new",
        {
            "edit_id": edit.id,
            "parent_id": parent_id,
        },
        project_id=project_id,
    )
    return edit.serialize(obj_type="Edit")


def update_edit(edit_id, data_dict):
    """
    Update fields of an edit with a given edit_id with data given data_dict.
    """
    edit = get_edit_raw(edit_id)
    edit.update(data_dict)
    clear_edit_cache(edit_id)
    events.emit(
        "edit:update", {"edit_id": edit_id}, project_id=str(edit.project_id)
    )
    return edit.serialize()


def get_edit_versions(edit_id):
    """
    Edit metadata changes are versioned. This function returns all versions
    of a given edit.
    """
    versions = (
        EntityVersion.query.filter_by(entity_id=edit_id)
        .order_by(EntityVersion.created_at.desc())
        .all()
    )
    return EntityVersion.serialize_list(versions, obj_type="EditVersion")
