from sqlalchemy import cast, Text
from sqlalchemy.orm import aliased
from sqlalchemy.exc import StatementError

from zou.app.utils import (
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app import db
from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityVersion,
    EntityConceptLink,
)
from zou.app.models.project import Project
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task

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
    cache.cache.delete_memoized(get_edit, edit_id, True)
    cache.cache.delete_memoized(get_full_edit, edit_id)


@cache.memoize_function(1200)
def get_edit_type():
    return entities_service.get_temporal_entity_type_by_name("Edit")


def get_edits(criterions=None):
    """
    Get all edits for given criterions.
    """
    if criterions is None:
        criterions = {}
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


EDITS_AND_TASKS_TASK_FIELDS = [
    "id",
    "duration",
    "due_date",
    "entity_id",
    "end_date",
    "estimation",
    "last_comment_date",
    "last_preview_file_id",
    "nb_assets_ready",
    "priority",
    "real_start_date",
    "retake_count",
    "start_date",
    "task_status_id",
    "task_type_id",
]


def get_edits_and_tasks(criterions=None):
    """
    Get all edits for given criterions with related tasks for each edit,
    as a list of dicts. Flat narrow queries through
    entities_service.fetch_entity_task_map instead of a row-multiplying
    join; response shape unchanged.
    """
    if criterions is None:
        criterions = {}
    edit_type = get_edit_type()
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), edit_type["id"]
    )

    assigned_to = "assigned_to" in criterions
    if assigned_to:
        del criterions["assigned_to"]

    Episode = aliased(Entity, name="episode")

    def apply_filters(query):
        query = query.filter(Entity.entity_type_id == edit_type["id"])
        if "id" in criterions:
            query = query.filter(Entity.id == criterions["id"])
        if "project_id" in criterions:
            query = query.filter(Entity.project_id == criterions["project_id"])
        if "episode_id" in criterions:
            query = query.filter(Entity.parent_id == criterions["episode_id"])
        if assigned_to:
            has_assigned_task = (
                db.session.query(Task.id)
                .filter(Task.entity_id == Entity.id)
                .filter(user_service.build_assignee_filter())
                .exists()
            )
            query = query.filter(has_assigned_task)
        return query

    edit_rows = (
        apply_filters(
            Entity.query.join(
                Project, Entity.project_id == Project.id
            ).outerjoin(Episode, Episode.id == Entity.parent_id)
        )
        .with_entities(
            cast(Entity.id, Text).label("id"),
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.canceled,
            cast(Entity.entity_type_id, Text).label("entity_type_id"),
            cast(Entity.parent_id, Text).label("parent_id"),
            cast(Entity.preview_file_id, Text).label("preview_file_id"),
            cast(Entity.source_id, Text).label("source_id"),
            Entity.nb_entities_out,
            cast(Entity.project_id, Text).label("project_id"),
            cast(Episode.id, Text).label("episode_id"),
            Episode.name.label("episode_name"),
            Project.name.label("project_name"),
        )
        .all()
    )

    tasks_by_entity, build_task = entities_service.fetch_entity_task_map(
        apply_filters,
        subscription_map,
        EDITS_AND_TASKS_TASK_FIELDS,
        assigned_to=assigned_to,
    )

    not_allowed_map = None
    if "vendor_departments" in criterions:
        not_allowed_map = (
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                "Edit",
                criterions["vendor_departments"],
                set(row.project_id for row in edit_rows),
            )
        )

    edits = []
    for row in edit_rows:
        data = fields.serialize_value(row.data or {})
        if not_allowed_map is not None:
            data = entities_service.remove_not_allowed_fields_from_metadata(
                not_allowed_map[row.project_id], data
            )
        edits.append(
            {
                "canceled": row.canceled,
                "data": data,
                "description": row.description,
                "entity_type_id": row.entity_type_id,
                "episode_id": row.episode_id,
                "episode_name": row.episode_name or "",
                "id": row.id,
                "name": row.name,
                "parent_id": row.parent_id,
                "preview_file_id": row.preview_file_id,
                "project_id": row.project_id,
                "project_name": row.project_name,
                "source_id": row.source_id,
                "nb_entities_out": row.nb_entities_out,
                "tasks": [
                    build_task(task_row)
                    for task_row in tasks_by_entity.get(row.id, ())
                ],
                "type": "Edit",
            }
        )
    return edits


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
def get_edit(edit_id, relations=False):
    """
    Return given edit as a dictionary.
    """
    return get_edit_raw(edit_id).serialize(
        obj_type="Edit", relations=relations
    )


@cache.memoize_function_single_flight(120)
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
    return entities_service.is_edit(entity)


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
        ScheduleItem.delete_all_by(object_id=edit_id)
        EntityLink.delete_all_by(entity_in_id=edit_id)
        EntityLink.delete_all_by(entity_out_id=edit_id)
        EntityConceptLink.delete_all_by(entity_in_id=edit_id)
        EntityConceptLink.delete_all_by(entity_out_id=edit_id)

        edit.delete()
        clear_edit_cache(edit_id)
        events.emit(
            "edit:delete",
            {"edit_id": edit_id},
            project_id=str(edit.project_id),
        )

    deleted_edit = edit.serialize(obj_type="Edit")
    return deleted_edit


def create_edit(
    project_id, name, data={}, description="", parent_id=None, created_by=None
):
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
            created_by=created_by,
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
