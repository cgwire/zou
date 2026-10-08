"""
Business logic for tasks: assignation, status changes, comments, time
spent and the aggregated "todos"/"open tasks" views.

Two conventions matter when editing this module:
- get_task()/get_task_status()/... return serialized dicts and are
  memoized; every mutation must invalidate its entry (clear_task_cache
  and friends) or clients keep reading stale data.
- Several imports of other services are done lazily inside functions to
  break import cycles (tasks <-> shots <-> entities). Keep them local
  when adding cross-service calls.
"""

import collections
import dataclasses
from typing import Optional

from sqlalchemy import and_, any_, cast
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import StaleDataError

from zou.app import db
from zou.app.utils import events

from zou.app.models.comment import (
    Comment,
)
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType, TaskTypeAssetTypeLink
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import (
    Project,
    ProjectPersonLink,
    ProjectTaskTypeLink,
)
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.models.time_spent import TimeSpent

from zou.app.utils import (
    cache,
    fields,
    date_helpers,
)


from zou.app.exceptions import (
    EpisodeNotFoundException,
    PersonNotFoundException,
    RevisionAlreadyExistsException,
    TaskNotFoundException,
    WrongParameterException,
)

from zou.app.services import (
    assets_service,
    base_service,
    concepts_service,
    edits_service,
    entities_service,
    files_service,
    persons_service,
    projects_service,
    shots_service,
    departments_service,
    entity_types_service,
    subscriptions_service,
    task_types_service,
)


def clear_task_cache(task_id):
    """
    Drop every memoized serialization of given task.
    """
    cache.cache.delete_memoized(_get_task_cached, str(task_id), False)
    cache.cache.delete_memoized(_get_task_cached, str(task_id), True)


def get_department_from_task(task_id):
    """
    Get department of given task as dictionary
    """
    task = get_task_raw(task_id)
    return departments_service.get_department_from_task_type(task.task_type_id)


def get_task_raw(task_id):
    """
    Get task matching given id as an active record.
    """
    return base_service.get_instance(Task, task_id, TaskNotFoundException)


@cache.memoize_function(120)
def _get_task_cached(task_id, relations):
    return get_task_raw(task_id).serialize(relations=relations)


def get_task(task_id, relations=False):
    """
    Get task matching given id as a dictionary.

    The id is normalized to a string before it reaches the cache: a UUID
    and its string form would otherwise be two entries, and only the string
    one is ever invalidated by clear_task_cache.
    """
    return _get_task_cached(str(task_id), bool(relations))


def get_task_by_shotgun_id(shotgun_id):
    """
    Get task matching given shotgun id as a dictionary.
    """
    task = Task.get_by(shotgun_id=shotgun_id)
    if task is None:
        raise TaskNotFoundException
    return task.serialize()


def get_tasks_for_shot(shot_id, relations=False):
    """
    Get all tasks for given shot.
    """
    shot = shots_service.get_shot(shot_id)
    return get_task_dicts_for_entity(shot["id"], relations=relations)


def get_tasks_for_scene(scene_id, relations=False):
    """
    Get all tasks for given scene.
    """
    scene = shots_service.get_scene(scene_id)
    return get_task_dicts_for_entity(scene["id"], relations=relations)


def get_tasks_for_sequence(sequence_id, relations=False):
    """
    Get all tasks for given sequence.
    """
    sequence = shots_service.get_sequence(sequence_id)
    return get_task_dicts_for_entity(sequence["id"], relations=relations)


def get_tasks_for_asset(asset_id, relations=False):
    """
    Get all tasks for given asset.
    """
    asset = assets_service.get_asset_raw(asset_id)
    return get_task_dicts_for_entity(asset.id, relations=relations)


def get_tasks_for_episode(episode_id, relations=False):
    """
    Get all tasks for given episode.
    """
    episode = shots_service.get_episode_raw(episode_id)
    return get_task_dicts_for_entity(episode.id, relations=relations)


def get_tasks_for_edit(edit_id, relations=False):
    """
    Get all tasks for given edit.
    """
    edit = edits_service.get_edit(edit_id)
    return get_task_dicts_for_entity(edit["id"], relations=relations)


def get_tasks_for_concept(concept_id, relations=False):
    """
    Get all tasks for given concept.
    """
    concept = concepts_service.get_concept(concept_id)
    return get_task_dicts_for_entity(concept["id"], relations=relations)


def get_shot_tasks_for_sequence(sequence_id, relations=False):
    """
    Get all shot tasks for given sequence.
    """
    query = _get_entity_task_query(relations=relations)
    query = query.filter(Entity.parent_id == sequence_id)
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_shot_tasks_for_episode(episode_id, relations=False):
    """
    Get all shots tasks for given episode.
    """
    query = _get_entity_task_query(relations=relations)
    Sequence = aliased(Entity, name="sequence")
    query = query.join(Sequence, Entity.parent_id == Sequence.id).filter(
        Sequence.parent_id == episode_id
    )
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_edit_tasks_for_episode(episode_id, relations=False):
    """
    Get all edit tasks for given episode.
    """
    query = (
        _get_entity_task_query(relations=relations)
        # An edit hangs straight off its episode, where a shot goes through
        # a sequence, so the entity type is what tells them apart here.
        .filter(
            Entity.entity_type_id == entity_types_service.get_edit_type()["id"]
        ).filter(Entity.parent_id == episode_id)
    )
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_asset_tasks_for_episode(episode_id, relations=False):
    """
    Get all assets tasks for given episode.
    """
    query = (
        _get_entity_task_query(relations=relations)
        .filter(entity_types_service.build_asset_type_filter())
        .filter(Entity.source_id == episode_id)
    )
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_task_dicts_for_entity(entity_id, relations=True):
    """
    Return all tasks related to given entity. Add extra information like
    project name, task type name, etc.
    """
    query = _get_entity_task_query(relations=relations)
    query = query.filter(Task.entity_id == entity_id)
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def _get_entity_task_query(relations=False):
    """
    Base query joining a task to everything the detailed task view needs:
    project, task type, task status, entity and assignees. No SQL
    ordering: sorting thousands of wide task rows (JSONB data included)
    made PostgreSQL materialize the whole join, the caller sorts the
    serialized dicts instead.
    """
    return (
        Task.query.join(Project, Task.project_id == Project.id)
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .join(Entity, Task.entity_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .add_columns(Project.name)
        .add_columns(TaskType.name)
        .add_columns(TaskStatus.name)
        .add_columns(EntityType.name)
        .add_columns(Entity.name)
    )


def _convert_rows_to_detailed_tasks(rows, relations=False):
    """
    Turn the rows of _get_entity_task_query into the task dicts the API
    returns, assignee ids included.
    """
    task_dicts = [
        {
            **task_object.serialize(relations=False),
            "project_name": project_name,
            "task_type_name": task_type_name,
            "task_status_name": task_status_name,
            "entity_type_name": entity_type_name,
            "entity_name": entity_name,
        }
        for task_object, project_name, task_type_name, task_status_name, entity_type_name, entity_name in rows
    ]
    task_dicts.sort(
        key=lambda task: (
            task["name"].casefold(),
            task["project_name"].casefold(),
            task["task_type_name"].casefold(),
            task["entity_type_name"].casefold(),
            task["entity_name"].casefold(),
        )
    )
    if relations and task_dicts:
        attach_assignee_ids(task_dicts)
    return task_dicts


def attach_assignee_ids(task_dicts):
    """
    Fetch all assignees for the given tasks in a single query and inject the
    list of person ids into each dict. Avoids the N+1 that occurs when each
    Task row triggers a separate lazy load of its assignees relationship.
    """
    task_ids = [task["id"] for task in task_dicts]
    links = (
        db.session.query(TaskPersonLink.task_id, TaskPersonLink.person_id)
        # One array parameter: an IN list binds one parameter per task,
        # which takes seconds on a full episode.
        .filter(
            TaskPersonLink.task_id == any_(cast(task_ids, ARRAY(UUID)))
        ).all()
    )
    assignees_by_task = collections.defaultdict(list)
    for task_id, person_id in links:
        assignees_by_task[str(task_id)].append(str(person_id))
    for task in task_dicts:
        task["assignees"] = assignees_by_task.get(task["id"], [])


def resolve_episode_and_build_task_dict(
    task,
    project_name,
    project_has_avatar,
    entity_id,
    entity_name,
    entity_description,
    entity_data,
    entity_preview_file_id,
    entity_type_name,
    entity_canceled,
    entity_parent_id,
    entity_source_id,
    sequence_name,
    episode_id,
    episode_name,
    task_type_name,
    task_type_for_entity,
    task_status_name,
    task_type_color,
    task_status_color,
    task_status_short_name,
):
    """
    Resolve episode info and build the base task dict with common fields.
    Returns (task_dict, task, task_type_name, task_type_for_entity,
    task_status_name, task_type_color, task_status_color,
    task_status_short_name).
    """
    if entity_preview_file_id is None:
        entity_preview_file_id = ""
    if entity_source_id is None:
        entity_source_id = ""
    if episode_id is None:
        episode_id = entity_source_id
        if episode_id is not None and episode_id != "":
            try:
                episode = shots_service.get_episode(episode_id)
                episode_name = episode["name"]
            except EpisodeNotFoundException:
                episode_name = "MP"

    # Serialize the Task instance already carried by the row instead of
    # re-fetching it through get_task (one query per row on cache miss).
    # Assignees are attached in batch by the callers.
    task_dict = task.serialize()
    if entity_type_name == "Sequence" and entity_parent_id is not None:
        episode_id = entity_parent_id
        episode = shots_service.get_episode(episode_id)
        episode_name = episode["name"]

    task_dict.update(
        {
            "project_name": project_name,
            "project_id": str(task.project_id),
            "project_has_avatar": project_has_avatar,
            "entity_id": str(entity_id),
            "entity_name": entity_name,
            "entity_description": entity_description,
            "entity_data": entity_data,
            "entity_preview_file_id": str(entity_preview_file_id),
            "entity_source_id": str(entity_source_id),
            "entity_type_name": entity_type_name,
            "entity_canceled": entity_canceled,
            "sequence_name": sequence_name,
            "episode_id": str(episode_id),
            "episode_name": episode_name,
            "task_type_for_entity": task_type_for_entity,
        }
    )
    return (
        task_dict,
        task,
        task_type_name,
        task_status_name,
        task_type_color,
        task_status_color,
        task_status_short_name,
    )


def add_last_comments_to_tasks(tasks):
    """
    For each task, add the last comment info.
    """
    task_ids = [task["id"] for task in tasks]
    task_comment_map = get_last_comment_map(task_ids)
    for task in tasks:
        task["last_comment"] = task_comment_map.get(task["id"], {})


def get_task_types_for_shot(shot_id):
    """
    Return all task types for which there is a task related to given shot.
    """
    return get_task_types_for_entity(shot_id)


def get_task_types_for_scene(scene_id):
    """
    Return all task types for which there is a task related to given scene.
    """
    return get_task_types_for_entity(scene_id)


def get_task_types_for_sequence(sequence_id):
    """
    Return all task types for which there is a task related to given sequence.
    """
    Sequence = aliased(Entity, name="sequence")
    task_types = (
        TaskType.query.join(Task)
        .join(Entity)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .filter(Sequence.id == sequence_id)
        .group_by(TaskType.id)
        .all()
    )
    return fields.serialize_models(task_types)


def get_task_types_for_asset(asset_id):
    """
    Return all task types for which there is a task related to given asset.
    """
    return get_task_types_for_entity(asset_id)


def get_task_types_for_episode(episode_id):
    """
    Return all task types for which there is a task related to given episode.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    task_types = (
        TaskType.query.join(Task)
        .join(Entity)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .join(Episode, Episode.id == Sequence.parent_id)
        .filter(Episode.id == episode_id)
        .group_by(TaskType.id)
        .all()
    )
    return fields.serialize_models(task_types)


def get_task_types_for_concept(concept_id):
    """
    Return all task types for which there is a task related to given concept.
    """
    return get_task_types_for_entity(concept_id)


def get_task_types_for_entity(entity_id):
    """
    Return all task types for which there is a task related to given entity.
    """
    task_types = (
        TaskType.query.join(Task)
        .join(Entity)
        .filter(Entity.id == entity_id)
        .distinct()
        .all()
    )
    return fields.serialize_models(task_types)


def get_task_types_for_project(project_id):
    """
    Return all task types for which there is a task related to given project.
    """
    task_types = (
        TaskType.query.join(Task)
        .filter(Task.project_id == project_id)
        .distinct(TaskType.id)
        .all()
    )
    return fields.serialize_models(task_types)


def get_task_types_for_edit(edit_id):
    """
    Return all task types for which there is a task related to given edit.
    """
    return get_task_types_for_entity(edit_id)


def get_next_preview_revision(task_id):
    """
    Get upcoming revision for preview files of given task.
    """
    preview_files = (
        PreviewFile.query.filter_by(task_id=task_id)
        .order_by(PreviewFile.revision.desc())
        .all()
    )
    revision = 1
    if len(preview_files) > 0:
        revision = preview_files[0].revision + 1
    return revision


def get_next_position(task_id, revision):
    """
    Get upcoming position for preview files of given task and revision.
    """
    preview_files = PreviewFile.query.filter_by(
        task_id=task_id, revision=revision
    ).all()
    return len(preview_files) + 1


def get_comment_by_preview_file_id(preview_file_id):
    """
    Return comment related to given preview file as a dict.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    comment = Comment.query.filter(
        Comment.previews.contains(preview_file)
    ).first()
    if comment is not None:
        return comment.serialize()
    else:
        return None


def get_tasks_for_entity_and_task_type(entity_id, task_type_id):
    """
    For a task type, returns all tasks related to given entity.
    """
    tasks = (
        Task.query.filter_by(entity_id=entity_id, task_type_id=task_type_id)
        .order_by(Task.name)
        .all()
    )
    return Task.serialize_list(tasks)


def get_tasks_for_project_and_task_type(project_id, task_type_id):
    """
    For a project and a task type returns all tasks.
    """
    tasks = (
        Task.query.filter_by(project_id=project_id, task_type_id=task_type_id)
        .order_by(Task.name)
        .all()
    )
    return Task.serialize_list(tasks)


def get_last_comment_map(task_ids):
    """
    Return the last comment of each given task, in one query.
    """
    task_comment_map = {}
    comments = (
        Comment.query.filter(Comment.object_id.in_(task_ids))
        .join(Person, Comment.person_id == Person.id)
        .join(Task, Comment.object_id == Task.id)
        .outerjoin(
            ProjectPersonLink,
            and_(
                ProjectPersonLink.person_id == Person.id,
                ProjectPersonLink.project_id == Task.project_id,
            ),
        )
        .filter(func.coalesce(ProjectPersonLink.role, Person.role) != "client")
        .order_by(Comment.object_id, Comment.created_at)
        .all()
    )
    for comment in comments:
        task_id = fields.serialize_value(comment.object_id)
        task_comment_map[task_id] = {
            "text": comment.text,
            "date": fields.serialize_value(comment.created_at),
            "person_id": fields.serialize_value(comment.person_id),
        }
    return task_comment_map


def _build_task_no_commit(task_type, task_status, entity, current_user_id):
    """
    Insert a new task (without committing) using the zou defaults for
    name, durations, dates and assignees.
    """
    return Task.create_no_commit(
        name="main",
        duration=0,
        estimation=0,
        completion_rate=0,
        start_date=None,
        end_date=None,
        due_date=None,
        real_start_date=None,
        project_id=entity["project_id"],
        task_type_id=task_type["id"],
        task_status_id=task_status["id"],
        entity_id=entity["id"],
        assigner_id=current_user_id,
        assignees=[],
    )


def create_tasks(task_type, entities):
    """
    Create a new task for given task type and for each entity.
    """
    if not entities:
        return []

    current_user_id = None
    try:
        current_user_id = persons_service.get_current_user()["id"]
    except RuntimeError:
        pass

    entity_ids = [entity["id"] for entity in entities]
    existing_tasks = Task.query.filter(
        Task.entity_id.in_(entity_ids), Task.task_type_id == task_type["id"]
    ).all()
    existing_entity_ids = {str(task.entity_id) for task in existing_tasks}

    task_status = task_types_service.get_default_task_status(
        for_concept=entities[0]["entity_type_id"]
        == entity_types_service.get_concept_type()["id"]
    )

    tasks = []
    for entity in entities:
        if str(entity["id"]) not in existing_entity_ids:
            tasks.append(
                _build_task_no_commit(
                    task_type, task_status, entity, current_user_id
                )
            )
    Task.commit()

    return [
        _finalize_task_creation(task_type, task_status, task) for task in tasks
    ]


def create_tasks_for_entity(entity, task_types=None):
    """
    Create tasks of multiple types for a single entity in one batch.
    When task_types is empty or None, default to every task type valid
    for the entity: enabled in the project, in the asset-type workflow
    (for assets), and whose for_entity matches the entity kind. When a
    list is provided, each task type is validated against those same
    constraints. An asset type with no configured workflow accepts every
    task type. Existing tasks for the same (entity, task_type,
    name="main") are skipped.
    """
    project_id = entity["project_id"]
    is_asset = entity_types_service.is_asset_dict(entity)
    if is_asset:
        entity_kind = "Asset"
    else:
        entity_type = entity_types_service.get_entity_type(
            entity["entity_type_id"]
        )
        entity_kind = entity_type["name"]

    enabled_in_project = {
        str(link.task_type_id)
        for link in ProjectTaskTypeLink.query.filter(
            ProjectTaskTypeLink.project_id == project_id
        ).all()
    }
    # None means unrestricted: not an asset, or no workflow configured
    # on the asset type ("Includes all asset task types" in Kitsu).
    enabled_in_workflow = None
    if is_asset:
        enabled_in_workflow = {
            str(link.task_type_id)
            for link in TaskTypeAssetTypeLink.query.filter(
                TaskTypeAssetTypeLink.asset_type_id == entity["entity_type_id"]
            ).all()
        } or None

    if not task_types:
        candidate_ids = enabled_in_project
        if enabled_in_workflow is not None:
            candidate_ids = candidate_ids & enabled_in_workflow
        if not candidate_ids:
            return []
        task_types = [
            task_type.serialize()
            for task_type in TaskType.query.filter(
                TaskType.id.in_(candidate_ids)
            ).all()
            if not task_type.for_entity or task_type.for_entity == entity_kind
        ]
        if not task_types:
            return []
    else:
        for task_type in task_types:
            type_id = task_type["id"]
            expected = task_type.get("for_entity")
            if expected and expected != entity_kind:
                raise WrongParameterException(
                    f"Task type {type_id} is for {expected} entities, "
                    f"got {entity_kind}."
                )
            if str(type_id) not in enabled_in_project:
                raise WrongParameterException(
                    f"Task type {type_id} is not enabled in project "
                    f"{project_id}."
                )
            if (
                enabled_in_workflow is not None
                and str(type_id) not in enabled_in_workflow
            ):
                raise WrongParameterException(
                    f"Task type {type_id} is not in the workflow of "
                    f"asset type {entity['entity_type_id']}."
                )

    type_ids = [task_type["id"] for task_type in task_types]
    existing_type_ids = {
        str(task.task_type_id)
        for task in Task.query.filter(
            Task.entity_id == entity["id"],
            Task.task_type_id.in_(type_ids),
            Task.name == "main",
        ).all()
    }

    task_status = task_types_service.get_default_task_status(
        for_concept=entity["entity_type_id"]
        == entity_types_service.get_concept_type()["id"]
    )
    current_user_id = None
    try:
        current_user_id = persons_service.get_current_user()["id"]
    except RuntimeError:
        pass

    new_tasks = []
    for task_type in task_types:
        if str(task_type["id"]) in existing_type_ids:
            continue
        task = _build_task_no_commit(
            task_type, task_status, entity, current_user_id
        )
        new_tasks.append((task_type, task))
    Task.commit()

    return [
        _finalize_task_creation(task_type, task_status, task)
        for task_type, task in new_tasks
    ]


def create_task(task_type, entity, name="main"):
    """
    Create a new task for given task type and entity.
    """
    task_status = task_types_service.get_default_task_status(
        for_concept=entity["entity_type_id"]
        == entity_types_service.get_concept_type()["id"]
    )
    try:
        try:
            current_user_id = persons_service.get_current_user()["id"]
        except RuntimeError:
            current_user_id = None
        task = Task.create(
            name=name,
            duration=0,
            estimation=0,
            completion_rate=0,
            start_date=None,
            end_date=None,
            due_date=None,
            real_start_date=None,
            project_id=entity["project_id"],
            task_type_id=task_type["id"],
            task_status_id=task_status["id"],
            entity_id=entity["id"],
            assigner_id=current_user_id,
            assignees=[],
        )
        task_dict = _finalize_task_creation(task_type, task_status, task)
        return task_dict
    except IntegrityError:
        pass  # Tasks already exists, no need to create it.
    return None


def _finalize_task_creation(task_type, task_status, task):
    """
    Run what follows the insert of a task: cache invalidation and the
    task:new event.
    """
    task_dict = task.serialize()
    task_dict["assignees"] = []
    task_dict.update(
        {
            "task_status_id": task_status["id"],
            "task_status_name": task_status["name"],
            "task_status_short_name": task_status["short_name"],
            "task_status_color": task_status["color"],
            "task_type_id": task_type["id"],
            "task_type_name": task_type.get("name", ""),
            "task_type_color": task_type.get("color", ""),
            "task_type_priority": task_type.get("priority", ""),
        }
    )
    events.emit(
        "task:new", {"task_id": task.id}, project_id=task_dict["project_id"]
    )
    return task_dict


def update_task(task_id, data):
    """
    Update task with given data.
    """
    task = get_task_raw(task_id)

    if "task_status_id" in data and data["task_status_id"] != str(
        task.task_status_id
    ):
        new_status = task_types_service.get_task_status_raw(
            data["task_status_id"]
        )
        now = date_helpers.get_utc_now_datetime()
        # Rolling a task back from done/feedback must clear the matching
        # dates, otherwise stats keep counting the task as finished.
        if new_status.is_feedback_request:
            data["end_date"] = now
        elif not new_status.is_done:
            data["end_date"] = None
        data["done_date"] = now if new_status.is_done else None

    task.update(data)
    clear_task_cache(task_id)
    events.emit(
        "task:update", {"task_id": task_id}, project_id=str(task.project_id)
    )
    return task.serialize()


def clear_assignation(task_id, person_id=None):
    """
    Clear task assignation and emit a *task:unassign* event.
    """
    task = get_task_raw(task_id)
    project_id = str(task.project_id)

    if person_id is None:
        removed_assignments = [person.serialize() for person in task.assignees]
        new_assignees = []
    else:
        removed_assignments = [{"id": person_id}]
        new_assignees = [
            person for person in task.assignees if str(person.id) != person_id
        ]

    try:
        task.update({"assignees": new_assignees})
    except StaleDataError:
        # A concurrent unassign already removed the link, so the desired state
        # is already reached. task.update() has rolled back its own failed
        # transaction, so there is nothing left to delete: treat it as cleared.
        pass

    clear_task_cache(task_id)
    task_dict = task.serialize()
    for assignee in removed_assignments:
        events.emit(
            "task:unassign",
            {"person_id": assignee["id"], "task_id": task_id},
            project_id=project_id,
        )
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)
    return task_dict


def assign_task(task_id, person_id, assigner_id=None):
    """
    Assign given person to given task. Emit a *task:assign* event.
    """
    task = get_task_raw(task_id)
    project_id = str(task.project_id)
    person = persons_service.get_person_raw(person_id)
    if person not in task.assignees:
        task.assignees.append(person)
    if assigner_id is not None:
        task.assigner_id = assigner_id
    task.save()
    task_dict = task.serialize(relations=True)
    clear_task_cache(task_id)
    events.emit(
        "task:assign",
        {"task_id": task.id, "person_id": person.id},
        project_id=project_id,
    )
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)
    return task_dict


def task_to_review(
    task_id, person, comment, preview_path=None, change_status=True
):
    """
    Deprecated
    Change the task status to "waiting for approval" if it is not already the
    case. It emits a *task:to-review* event.
    """
    if preview_path is None:
        preview_path = {}
    task = get_task_raw(task_id)
    to_review_status = task_types_service.get_to_review_status()
    task_dict_before = task.serialize()

    if change_status:
        task.update({"task_status_id": to_review_status["id"]})
        task.save()
        clear_task_cache(task_id)

    project = Project.get(task.project_id)
    entity = Entity.get(task.entity_id)
    entity_type = EntityType.get(entity.entity_type_id)

    task_dict_after = task.serialize()
    task_dict_after["project"] = project.serialize()
    task_dict_after["entity"] = entity.serialize()
    task_dict_after["entity_type"] = entity_type.serialize()
    task_dict_after["person"] = person
    task_dict_after["comment"] = comment
    task_dict_after["preview_path"] = preview_path

    events.emit(
        "task:to-review",
        {
            "task_id": task_id,
            "task_shotgun_id": task_dict_before["shotgun_id"],
            "entity_type_name": entity_type.name,
            "previous_task_status_id": task_dict_before["task_status_id"],
            "entity_shotgun_id": entity.shotgun_id,
            "project_shotgun_id": project.shotgun_id,
            "person_shotgun_id": person["shotgun_id"],
            "comment": comment,
            "preview_path": preview_path,
            "change_status": change_status,
        },
    )

    return task_dict_after


def check_revision_is_unique_for_task(
    task_id, revision, exclude_preview_id=None
):
    """
    Check that the revision number is unique for the given task.
    Raises RevisionAlreadyExistsException if a preview file with the same
    revision already exists for this task (at position 1).
    """
    query = PreviewFile.query.filter_by(
        task_id=task_id,
        revision=revision,
        position=1,
    )
    if exclude_preview_id is not None:
        query = query.filter(PreviewFile.id != exclude_preview_id)
    existing = query.first()
    if existing is not None:
        raise RevisionAlreadyExistsException(
            f"Revision {revision} already exists for this task. "
            "Choose a different revision number, or omit it to let the "
            "revision auto-increment."
        )


def update_preview_file_info(preview_file):
    """
    Refresh the task fields derived from its last preview: revision,
    last preview file id and preview counters.
    """
    entity = None
    task = get_task_raw(preview_file["task_id"])
    if preview_file["position"] == 1:
        task.update({"last_preview_file_id": preview_file["id"]})
        clear_task_cache(str(task.id))
        project = projects_service.get_project(str(task.project_id))

        if project["is_set_preview_automated"]:
            entity = entities_service.update_entity_preview(
                task.entity_id,
                preview_file["id"],
            )
    return entity


def get_project_tasks_fingerprint(project_id):
    """
    Return a cheap change signal for the tasks of given project: the
    latest update date and the row count. Any create, update, delete or
    assignation (assigning saves the task) moves at least one of them.
    """
    max_updated_at, task_count = (
        Task.query.with_entities(
            func.max(Task.updated_at), func.count(Task.id)
        )
        .filter(Task.project_id == project_id)
        .one()
    )
    return f"{max_updated_at}:{task_count}"


def get_full_task(task_id, user_id):
    """
    Return a task with everything the task page displays: entity, project,
    task type, status, assignees, time spents and subscription state.
    """
    task = get_task(task_id, relations=True)
    task_type = task_types_service.get_task_type(task["task_type_id"])
    project = projects_service.get_project(task["project_id"])
    task_status = task_types_service.get_task_status(task["task_status_id"])
    entity = entities_service.get_entity(task["entity_id"])
    entity_type = entity_types_service.get_entity_type(
        entity["entity_type_id"]
    )
    is_subscribed = subscriptions_service.is_person_subscribed(
        user_id, task_id
    )
    assignees = persons_service.get_persons_by_ids(task["assignees"])

    task.update(
        {
            "entity": entity,
            "entity_type": entity_type,
            "is_subscribed": is_subscribed,
            "persons": assignees,
            "project": project,
            "task_status": task_status,
            "task_type": task_type,
            "type": "Task",
        }
    )

    try:
        assigner = persons_service.get_person(task["assigner_id"])
        task["assigner"] = assigner
    except PersonNotFoundException:
        pass

    if entity["parent_id"] is not None:
        if entity_type["name"] == "Sequence":
            sequence = entity
        elif entity_type["name"] in ["Shot", "Scene"]:
            sequence = shots_service.get_sequence(entity["parent_id"])
        else:
            # Getting here means the entity is an asset, and assets are not
            # linked to specific sequences or episodes.
            return task

        task["sequence"] = sequence
        episode_id = sequence["parent_id"]
        if episode_id is not None:
            episode = shots_service.get_episode(episode_id)
            task["episode"] = episode

    return task


def reset_tasks_data(project_id):
    """
    Recompute the derived fields of every task of given project.
    """
    for task in Task.get_all_by(project_id=project_id):
        reset_task_data(str(task.id))


def reset_task_data(task_id):
    """
    Recompute the fields derived from the task comment history: status,
    retake count, start, end and last comment dates.
    """
    task = base_service.get_instance(Task, task_id, TaskNotFoundException)
    retake_count = 0
    real_start_date = None
    last_comment_date = None
    end_date = None
    done_date = None
    entity = entities_service.get_entity(task.entity_id)
    task_status_id = task_types_service.get_default_task_status(
        for_concept=entity["entity_type_id"]
        == entity_types_service.get_concept_type()["id"]
    )["id"]
    comments = (
        Comment.query.join(TaskStatus)
        .filter(Comment.object_id == task_id)
        .order_by(Comment.created_at)
        .add_columns(
            TaskStatus.is_retake,
            TaskStatus.is_feedback_request,
            TaskStatus.is_done,
            TaskStatus.is_wip,
        )
        .all()
    )

    previous_is_retake = False
    for (
        comment,
        task_status_is_retake,
        task_status_is_feedback_request,
        task_status_is_done,
        task_status_is_wip,
    ) in comments:
        if task_status_is_retake and not previous_is_retake:
            retake_count += 1
        previous_is_retake = task_status_is_retake

        if task_status_is_wip and real_start_date is None:
            real_start_date = comment.created_at

        if task_status_is_feedback_request and end_date is None:
            end_date = comment.created_at

        if task_status_is_done:
            done_date = comment.created_at

        task_status_id = comment.task_status_id
        last_comment_date = comment.created_at

    duration = 0
    time_spents = TimeSpent.get_all_by(task_id=task.id)
    for time_spent in time_spents:
        duration += time_spent.duration

    task.update(
        {
            "duration": duration,
            "retake_count": retake_count,
            "real_start_date": real_start_date,
            "last_comment_date": last_comment_date,
            "end_date": end_date,
            "done_date": done_date,
            "task_status_id": task_status_id,
        }
    )
    # Invalidate after the write, otherwise a concurrent read re-caches
    # the stale row between the invalidation and the update.
    clear_task_cache(task_id)
    project_id = str(task.project_id)
    events.emit(
        "task:update", {"task_id": str(task.id)}, project_id=project_id
    )
    return task.serialize(relations=True)


@dataclasses.dataclass
class OpenTasksFilters:
    """
    Criteria of the open task listings: the listing, its stats and the
    burndown read the same object so the three queries always agree on
    which tasks are in the pool.
    """

    task_type_id: Optional[str] = None
    task_status_id: Optional[str] = None
    project_id: Optional[str] = None
    person_id: Optional[str] = None
    studio_id: Optional[str] = None
    department_id: Optional[str] = None
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[int] = None

    @classmethod
    def from_args(cls, args):
        """
        Build the filters from the parsed query arguments of a route.
        """
        return cls(
            **{
                field.name: args.get(field.name)
                for field in dataclasses.fields(cls)
            }
        )
