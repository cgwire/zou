import collections
import uuid

from sqlalchemy.exc import StatementError, IntegrityError, DataError
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import case
from sqlalchemy.orm import aliased

from zou.app import app, db
from zou.app.utils import events

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import (
    Comment,
    acknowledgements_table,
    mentions_table,
    department_mentions_table,
    preview_link_table,
)
from zou.app.models.department import Department
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.news import News
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.models.task_status import TaskStatus
from zou.app.models.time_spent import TimeSpent
from zou.app.models.studio import Studio

from zou.app.utils import (
    cache,
    fields,
    query as query_utils,
    permissions,
    date_helpers,
)


from zou.app.services.exception import (
    CommentNotFoundException,
    EpisodeNotFoundException,
    PersonNotFoundException,
    TaskNotFoundException,
    TaskStatusNotFoundException,
    TaskTypeNotFoundException,
    DepartmentNotFoundException,
    StudioNotFoundException,
    WrongDateFormatException,
    TimeSpentNotFoundException,
)

from zou.app.services import (
    assets_service,
    edits_service,
    base_service,
    files_service,
    notifications_service,
    persons_service,
    projects_service,
    shots_service,
    entities_service,
    edits_service,
    concepts_service,
    user_service,
)


def clear_task_status_cache(task_status_id):
    cache.cache.delete_memoized(get_task_statuses)


def clear_task_type_cache(task_type_id):
    cache.cache.delete_memoized(get_task_type, task_type_id)
    cache.cache.delete_memoized(get_task_types)


def clear_department_cache(department_id):
    cache.cache.delete_memoized(get_department, department_id)
    cache.cache.delete_memoized(get_departments)


def clear_studio_cache(studio_id):
    cache.cache.delete_memoized(get_studio, studio_id)
    cache.cache.delete_memoized(get_studios)


def clear_task_cache(task_id):
    cache.cache.delete_memoized(get_task, task_id)
    cache.cache.delete_memoized(get_task, task_id, True)
    cache.cache.delete_memoized(get_task_with_relations, task_id)


@cache.memoize_function(120)
def clear_comment_cache(comment_id):
    cache.cache.delete_memoized(get_comment, comment_id)
    cache.cache.delete_memoized(get_comment_with_relations, comment_id)


@cache.memoize_function(120)
def get_departments():
    return fields.serialize_models(Department.get_all())


@cache.memoize_function(120)
def get_studios():
    return fields.serialize_models(Studio.get_all())


@cache.memoize_function(120)
def get_task_types():
    return fields.serialize_models(TaskType.get_all())


@cache.memoize_function(120)
def get_task_statuses():
    return fields.serialize_models(TaskStatus.get_all())


@cache.memoize_function(120)
def get_to_review_status():
    return get_or_create_status(app.config["TO_REVIEW_TASK_STATUS"], "pndng")


@cache.memoize_function(120)
def get_default_status(for_concept=False):
    if for_concept:
        return get_or_create_status(
            "Neutral",
            "neutral",
            "#CCCCCC",
            is_default=True,
            for_concept=True,
        )
    else:
        return get_or_create_status("Todo", "todo", "#f5f5f5", is_default=True)


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


@cache.memoize_function(120)
def get_department(department_id):
    """
    Get department matching given id as a dictionary.
    """
    try:
        department = Department.get(department_id)
    except StatementError:
        raise DepartmentNotFoundException

    if department is None:
        raise DepartmentNotFoundException

    return department.serialize()


@cache.memoize_function(120)
def get_studio(studio_id):
    """
    Get studio matching given id as a dictionary.
    """
    try:
        studio = Studio.get(studio_id)
    except StatementError:
        raise StudioNotFoundException

    if studio is None:
        raise StudioNotFoundException

    return studio.serialize()


def get_department_from_task_type(task_type_id):
    """
    Get department of given task type as dictionary
    """
    task_type = get_task_type_raw(task_type_id)
    return get_department(task_type.department_id)


def get_department_from_task(task_id):
    """
    Get department of given task as dictionary
    """
    task = get_task_raw(task_id)
    return get_department_from_task_type(task.task_type_id)


def get_task_type_raw(task_type_id):
    """
    Get task type matching given id as an active record.
    """
    try:
        task_type = TaskType.get(task_type_id)
    except StatementError:
        raise TaskTypeNotFoundException

    if task_type is None:
        raise TaskTypeNotFoundException

    return task_type


@cache.memoize_function(1200)
def get_task_type(task_type_id):
    """
    Get task type matching given id as a dictionary.
    """
    return get_task_type_raw(task_type_id).serialize()


def get_task_raw(task_id):
    """
    Get task matching given id as an active record.
    """
    try:
        task = Task.get(task_id)
    except StatementError:
        raise TaskNotFoundException

    if task is None:
        raise TaskNotFoundException

    return task


@cache.memoize_function(120)
def get_task(task_id, relations=False):
    """
    Get task matching given id as a dictionary.
    """
    return get_task_raw(task_id).serialize(relations=relations)


@cache.memoize_function(120)
def get_task_with_relations(task_id):
    """
    Get task matching given id as a dictionary.
    """
    return get_task_raw(task_id).serialize(relations=True)


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
    concept = shots_service.get_shot(concept_id)
    return get_task_dicts_for_entity(concept["id"], relations=relations)


def get_shot_tasks_for_sequence(sequence_id, relations=False):
    """
    Get all shot tasks for given sequence.
    """
    query = _get_entity_task_query()
    query = query.filter(Entity.parent_id == sequence_id)
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_shot_tasks_for_episode(episode_id, relations=False):
    """
    Get all shots tasks for given episode.
    """
    query = _get_entity_task_query()
    Sequence = aliased(Entity, name="sequence")
    query = query.join(Sequence, Entity.parent_id == Sequence.id).filter(
        Sequence.parent_id == episode_id
    )
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_asset_tasks_for_episode(episode_id, relations=False):
    """
    Get all assets tasks for given episode.
    """
    query = (
        _get_entity_task_query()
        .filter(assets_service.build_asset_type_filter())
        .filter(Entity.source_id == episode_id)
    )
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def get_task_dicts_for_entity(entity_id, relations=False):
    """
    Return all tasks related to given entity. Add extra information like
    project name, task type name, etc.
    """
    query = _get_entity_task_query()
    query = query.filter(Task.entity_id == entity_id)
    return _convert_rows_to_detailed_tasks(query.all(), relations)


def _get_entity_task_query():
    return (
        Task.query.order_by(Task.name)
        .join(Project, Task.project_id == Project.id)
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .join(Entity, Task.entity_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .add_columns(Project.name)
        .add_columns(TaskType.name)
        .add_columns(TaskStatus.name)
        .add_columns(EntityType.name)
        .add_columns(Entity.name)
        .order_by(Project.name, TaskType.name, EntityType.name, Entity.name)
    )


def _convert_rows_to_detailed_tasks(rows, relations=False):
    results = []
    for entry in rows:
        (
            task_object,
            project_name,
            task_type_name,
            task_status_name,
            entity_type_name,
            entity_name,
        ) = entry

        task = get_task_with_relations(str(task_object.id))
        task["project_name"] = project_name
        task["task_type_name"] = task_type_name
        task["task_status_name"] = task_status_name
        task["entity_type_name"] = entity_type_name
        task["entity_name"] = entity_name
        results.append(task)
    return results


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


def get_task_type_map():
    """
    Return a dict of which keys are task type ids and values are task types.
    """
    task_types = TaskType.query.all()
    return {
        str(task_type.id): task_type.serialize() for task_type in task_types
    }


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


def get_time_spents(task_id, date=None):
    """
    Return time spents for given task.
    """
    result = collections.defaultdict(list)
    result["total"] = 0
    time_spents = TimeSpent.query.filter_by(task_id=task_id)
    if date is not None:
        time_spents = time_spents.filter_by(
            date=func.cast(date, TimeSpent.date.type)
        )
    for time_spent in time_spents.all():
        result[str(time_spent.person_id)].append(time_spent.serialize())
        result["total"] += time_spent.duration
    return result


def get_comments(task_id, is_client=False, is_manager=False):
    """
    Return all comments related to given task.
    """
    comments = []
    query = _prepare_query(task_id, is_client, is_manager)
    (comments, comment_ids) = _run_task_comments_query(query)
    if len(comments) > 0:
        ack_map = _build_ack_map_for_comments(comment_ids)
        mention_map = _build_mention_map_for_comments(comment_ids)
        department_mention_map = _build_department_mention_map_for_comments(
            comment_ids
        )
        preview_map = _build_preview_map_for_comments(comment_ids, is_client)
        attachment_file_map = _build_attachment_map_for_comments(comment_ids)
        for comment in comments:
            comment["acknowledgements"] = ack_map.get(comment["id"], [])
            comment["previews"] = preview_map.get(comment["id"], [])
            comment["mentions"] = mention_map.get(comment["id"], [])
            comment["department_mentions"] = department_mention_map.get(
                comment["id"], []
            )
            comment["attachment_files"] = attachment_file_map.get(
                comment["id"], []
            )

    if is_client:
        tmp_comments = []
        task = get_task(task_id)
        project = projects_service.get_project(task["project_id"])
        for comment in comments:
            person = persons_service.get_person(comment["person_id"])
            current_user = persons_service.get_current_user()
            is_author = comment["person_id"] == current_user["id"]
            is_author_client = person["role"] == "client"
            is_clients_isolated = project.get("is_clients_isolated", False)
            is_allowed = (is_clients_isolated and is_author) or (
                not is_clients_isolated and is_author_client
            )
            if len(comment["previews"]) > 0 and not is_author_client:
                comment["text"] = ""
                comment["attachment_files"] = []
                comment["checklist"] = []
                tmp_comments.append(comment)
            elif is_allowed:
                tmp_comments.append(comment)
        comments = tmp_comments
    return comments


def _prepare_query(task_id, is_client, is_manager):
    query = (
        Comment.query.order_by(Comment.created_at.desc())
        .filter_by(object_id=task_id)
        .join(Person, Comment.person_id == Person.id)
        .join(TaskStatus, Comment.task_status_id == TaskStatus.id)
        .add_columns(
            TaskStatus.name,
            TaskStatus.short_name,
            TaskStatus.color,
            Person.first_name,
            Person.last_name,
            Person.has_avatar,
        )
    )
    if not is_manager and not is_client:
        query = query.filter(Person.role != "client")
    return query


def _run_task_comments_query(query):
    comment_ids = []
    comments = []
    for result in query.all():
        (
            comment,
            task_status_name,
            task_status_short_name,
            task_status_color,
            person_first_name,
            person_last_name,
            person_has_avatar,
        ) = result

        comment_dict = comment.serialize()
        comment_dict["person"] = {
            "first_name": person_first_name,
            "last_name": person_last_name,
            "has_avatar": person_has_avatar,
            "id": str(comment.person_id),
        }
        comment_dict["task_status"] = {
            "name": task_status_name,
            "short_name": task_status_short_name,
            "color": task_status_color,
            "id": str(comment.task_status_id),
        }
        comments.append(comment_dict)
        comment_ids.append(comment_dict["id"])
    return (comments, comment_ids)


def _build_ack_map_for_comments(comment_ids):
    ack_map = {}
    for link in (
        db.session.query(acknowledgements_table)
        .filter(acknowledgements_table.c.comment.in_(comment_ids))
        .all()
    ):
        comment_id = str(link.comment)
        person_id = str(link.person)
        if comment_id not in ack_map:
            ack_map[comment_id] = []
        ack_map[comment_id].append(person_id)
    return ack_map


def _build_mention_map_for_comments(comment_ids):
    mention_map = {}
    for link in (
        db.session.query(mentions_table)
        .filter(mentions_table.c.comment.in_(comment_ids))
        .all()
    ):
        comment_id = str(link.comment)
        person_id = str(link.person)
        if comment_id not in mention_map:
            mention_map[comment_id] = []
        mention_map[comment_id].append(person_id)
    return mention_map


def _build_department_mention_map_for_comments(comment_ids):
    mention_map = {}
    for link in (
        db.session.query(department_mentions_table)
        .filter(department_mentions_table.c.comment.in_(comment_ids))
        .all()
    ):
        comment_id = str(link.comment)
        department_id = str(link.department)
        if comment_id not in mention_map:
            mention_map[comment_id] = []
        mention_map[comment_id].append(department_id)
    return mention_map


def _build_preview_map_for_comments(comment_ids, is_client=False):
    preview_map = {}
    query = (
        PreviewFile.query.join(preview_link_table)
        .filter(preview_link_table.c.comment.in_(comment_ids))
        .add_columns(preview_link_table.c.comment)
    )
    for preview, comment_id in query.all():
        comment_id = str(comment_id)
        if comment_id not in preview_map:
            preview_map[comment_id] = []
        status = "ready"
        if preview.status is not None:
            status = preview.status.code
        validation_status = "neutral"
        if preview.validation_status is not None:
            validation_status = preview.validation_status.code

        if validation_status != "rejected" or not is_client:
            preview_map[comment_id].append(
                {
                    "id": str(preview.id),
                    "task_id": str(preview.task_id),
                    "revision": preview.revision,
                    "extension": preview.extension,
                    "width": preview.width,
                    "height": preview.height,
                    "duration": preview.duration,
                    "status": status,
                    "validation_status": validation_status,
                    "original_name": preview.original_name,
                    "position": preview.position,
                    "annotations": preview.annotations,
                }
            )
    return preview_map


def _build_attachment_map_for_comments(comment_ids):
    attachment_file_map = {}
    attachment_files = AttachmentFile.query.filter(
        AttachmentFile.comment_id.in_(comment_ids)
    ).all()
    for attachment_file in attachment_files:
        comment_id = str(attachment_file.comment_id)
        attachment_file_id = str(attachment_file.id)
        if comment_id not in attachment_file_map:
            attachment_file_map[str(comment_id)] = []
        attachment_file_map[str(comment_id)].append(
            {
                "id": attachment_file_id,
                "name": attachment_file.name,
                "extension": attachment_file.extension,
                "size": attachment_file.size,
            }
        )
    return attachment_file_map


def get_comment_raw(comment_id):
    """
    Return comment matching give id as an active record.
    """
    try:
        comment = Comment.get(comment_id)
    except StatementError:
        raise CommentNotFoundException

    if comment is None:
        raise CommentNotFoundException
    return comment


@cache.memoize_function(120)
def get_comment(comment_id):
    """
    Return comment matching give id as a dict.
    """
    comment = get_comment_raw(comment_id)
    return comment.serialize()


@cache.memoize_function(120)
def get_comment_with_relations(comment_id):
    """
    Return comment matching give id as a dict with joins information.
    """
    comment = get_comment_raw(comment_id)
    return comment.serialize(relations=True)


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


def get_task_status_map():
    """
    Return a dict of which keys are task status ids and values are task
    statuses.
    """
    return {
        str(status.id): status.serialize() for status in TaskStatus.query.all()
    }


def get_person_done_tasks(person_id, projects):
    """
    Return all finished tasks performed by a person.
    """
    return get_person_tasks(person_id, projects, is_done=True)


def get_person_related_tasks(person_id, task_type_id):
    """
    Retrieve all tasks for given task types and to entiities
    that have at least one person assignation.
    """
    person = Person.get(person_id)
    projects = projects_service.open_projects()
    project_ids = [project["id"] for project in projects]

    entities = (
        Entity.query.join(Task, Entity.id == Task.entity_id)
        .filter(Task.assignees.contains(person))
        .filter(Entity.project_id.in_(project_ids))
    ).all()

    entity_ids = [entity.id for entity in entities]
    tasks = (
        Task.query.filter(Task.entity_id.in_(entity_ids)).filter(
            Task.task_type_id == task_type_id
        )
    ).all()

    return fields.serialize_models(tasks)


def get_person_tasks(person_id, projects, is_done=None):
    """
    Retrieve all tasks for given person and projects.
    """
    person = Person.get(person_id)
    project_ids = [project["id"] for project in projects]

    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.join(Project, Task.project_id == Project.id)
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .filter(Task.assignees.contains(person))
        .filter(Project.id.in_(project_ids))
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Entity.source_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    )

    if is_done:
        query = query.filter(TaskStatus.is_done == True).order_by(
            Task.end_date.desc(), TaskType.name, Entity.name
        )
    else:
        query = query.filter(TaskStatus.is_done == False)

    # Add episodes linked to assets
    asset_ids = []
    for task in query.all():
        asset_ids.append(str(task[0].entity_id))

    cast_in_episode_ids = {}
    cast_in_episode_names = {}
    episode_links_query = (
        EntityLink.query.join(Episode, EntityLink.entity_in_id == Episode.id)
        .join(EntityType, EntityType.id == Episode.entity_type_id)
        .filter(EntityType.name == "Episode")
        .filter(EntityLink.entity_out_id.in_(asset_ids))
        .add_columns(Episode.id, Episode.name)
        .order_by(Episode.name)
    )
    for link, episode_id, episode_name in episode_links_query.all():
        asset_id = str(link.entity_out_id)
        if asset_id not in cast_in_episode_ids:
            cast_in_episode_ids[asset_id] = []
            cast_in_episode_names[asset_id] = []
        cast_in_episode_ids[asset_id].append(episode_id)
        cast_in_episode_names[asset_id].append(episode_name)

    # Build the result

    tasks = []
    for (
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
    ) in query.all():
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

        task_dict = get_task_with_relations(str(task.id))
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
                "task_estimation": task.estimation,
                "task_duration": task.duration,
                "task_start_date": fields.serialize_value(task.start_date),
                "task_due_date": fields.serialize_value(task.due_date),
                "task_type_name": task_type_name,
                "task_type_for_entity": task_type_for_entity,
                "task_status_name": task_status_name,
                "task_type_color": task_type_color,
                "task_status_color": task_status_color,
                "task_status_short_name": task_status_short_name,
            }
        )

        if str(task.entity_id) in cast_in_episode_ids:
            task_dict["episode_ids"] = cast_in_episode_ids[str(task.entity_id)]
            task_dict["episode_names"] = cast_in_episode_names[
                str(task.entity_id)
            ]
        tasks.append(task_dict)

    task_ids = [task["id"] for task in tasks]
    task_comment_map = get_last_comment_map(task_ids)
    for task in tasks:
        if task["id"] in task_comment_map:
            task["last_comment"] = task_comment_map[task["id"]]
        else:
            task["last_comment"] = {}
    return tasks


def get_person_tasks_to_check(project_ids=None, department_ids=None):
    """
    Retrieve all tasks requiring a feedback for given departments and projects.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    query = (
        Task.query.join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .join(TaskType, TaskType.id == Task.task_type_id)
        .join(TaskStatus, TaskStatus.id == Task.task_status_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .filter(TaskStatus.is_feedback_request)
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            Entity.source_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    )

    if project_ids is not None:
        query = query.filter(Project.id.in_(project_ids))
    else:
        query = query.filter(user_service.build_open_project_filter())

    if department_ids:
        query = query.filter(TaskType.department_id.in_(department_ids))
    tasks = []
    for (
        task,
        project_name,
        project_has_avatar,
        entity_id,
        entity_name,
        entity_description,
        entity_data,
        entity_preview_file_id,
        entity_source_id,
        entity_type_name,
        entity_canceled,
        entity_parent_id,
        sequence_name,
        episode_id,
        episode_name,
        task_type_name,
        task_type_for_entity,
        task_status_name,
        task_type_color,
        task_status_color,
        task_status_short_name,
    ) in query.all():
        if entity_preview_file_id is None:
            entity_preview_file_id = ""

        if entity_source_id is None:
            entity_source_id = ""

        if episode_id is None:
            episode_id = entity_source_id

        task_dict = get_task_with_relations(str(task.id))
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
                "task_estimation": task.estimation,
                "task_duration": task.duration,
                "task_start_date": fields.serialize_value(task.start_date),
                "task_due_date": fields.serialize_value(task.due_date),
                "task_type_name": task_type_name,
                "task_type_for_entity": task_type_for_entity,
                "task_status_name": task_status_name,
                "task_type_color": task_type_color,
                "task_status_color": task_status_color,
                "task_status_short_name": task_status_short_name,
            }
        )
        tasks.append(task_dict)

    task_ids = [task["id"] for task in tasks]
    task_comment_map = get_last_comment_map(task_ids)
    for task in tasks:
        if task["id"] in task_comment_map:
            task["last_comment"] = task_comment_map[task["id"]]
        else:
            task["last_comment"] = {}
    return tasks


def get_last_comment_map(task_ids):
    task_comment_map = {}
    comments = (
        Comment.query.filter(Comment.object_id.in_(task_ids))
        .join(Person)
        .filter(Person.role != "client")
        .order_by(Comment.object_id, Comment.created_at)
        .all()
    )
    task_id = None
    for comment in comments:
        if comment.object_id != task_id:
            task_id = fields.serialize_value(comment.object_id)
            task_comment_map[task_id] = {
                "text": comment.text,
                "date": fields.serialize_value(comment.created_at),
                "person_id": fields.serialize_value(comment.person_id),
            }
    return task_comment_map


def create_tasks(task_type, entities):
    """
    Create a new task for given task type and for each entity.
    """
    current_user_id = None
    try:
        current_user_id = persons_service.get_current_user()["id"]
    except RuntimeError:
        pass

    tasks = []
    for entity in entities:
        existing_task = Task.query.filter_by(
            entity_id=entity["id"], task_type_id=task_type["id"]
        ).scalar()
        if existing_task is None:
            task_status = get_default_status(
                for_concept=entity["entity_type_id"]
                == concepts_service.get_concept_type()["id"]
            )
            task = Task.create_no_commit(
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
            tasks.append(task)
    Task.commit()

    task_dicts = []
    for task in tasks:
        task_dict = _finalize_task_creation(task_type, task_status, task)
        task_dicts.append(task_dict)

    return task_dicts


def create_task(task_type, entity, name="main"):
    """
    Create a new task for given task type and entity.
    """
    task_status = get_default_status(
        for_concept=entity["entity_type_id"]
        == concepts_service.get_concept_type()["id"]
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

    if is_finished(task, data):
        data["end_date"] = date_helpers.get_utc_now_datetime()

    if is_done(task, data):
        data["done_date"] = date_helpers.get_utc_now_datetime()

    task.update(data)
    clear_task_cache(task_id)
    events.emit(
        "task:update", {"task_id": task_id}, project_id=str(task.project_id)
    )
    return task.serialize()


def get_or_create_status(
    name,
    short_name="",
    color="#f5f5f5",
    is_done=False,
    is_retake=False,
    is_feedback_request=False,
    is_default=False,
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
        )
        events.emit("task-status:new", {"task_status_id": task_status.id})
    return task_status.serialize()


def update_task_status(task_status_id, data):
    """
    Update task status data with given task_id.
    """
    task_status = get_task_status_raw(task_status_id)
    task_status.update(data)
    clear_task_status_cache(task_status_id)
    events.emit("task-status:update", {"task_status_id": task_status_id})
    return task_status.serialize()


def get_or_create_department(name, color="#000000"):
    """
    Create a new department it doesn't exist. If it exists, it returns the
    department from database.
    """
    department = Department.get_by(name=name)
    if department is None:
        department = Department(name=name, color=color)
        department.save()
        clear_department_cache(department.id)
        events.emit("department:new", {"department_id": department.id})
    return department.serialize()


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
    type from database.
    """
    task_type = TaskType.get_by(name=name)
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


def create_or_update_time_spent(task_id, person_id, date, duration, add=False):
    """
    Create a new time spent if it doesn't exist. If it exists, it update it
    with the new duration and returns it from the database.
    """
    try:
        time_spent = TimeSpent.get_by(
            task_id=task_id,
            person_id=person_id,
            date=func.cast(date, TimeSpent.date.type),
        )
    except DataError:
        raise WrongDateFormatException

    task = Task.get(task_id)
    project_id = str(task.project_id)
    if time_spent is not None:
        if add:
            time_spent.update({"duration": time_spent.duration + duration})
        else:
            time_spent.update({"duration": duration})
        events.emit(
            "time-spent:update",
            {"time_spent_id": str(time_spent.id)},
            project_id=project_id,
        )
    else:
        time_spent = TimeSpent.create(
            task_id=task_id, person_id=person_id, date=date, duration=duration
        )
        persons_service.update_person_last_presence(person_id)
        events.emit(
            "time-spent:new",
            {"time_spent_id": str(time_spent.id)},
            project_id=project_id,
        )

    task.duration = sum(
        time_spent.duration
        for time_spent in TimeSpent.get_all_by(task_id=task_id)
    )
    task.save()
    clear_task_cache(task_id)
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)

    return time_spent.serialize()


def delete_time_spent(task_id, person_id, date):
    """
    Delete time spent for given task, person and date.
    """
    try:
        time_spent = TimeSpent.get_by(
            task_id=task_id,
            person_id=person_id,
            date=func.cast(date, TimeSpent.date.type),
        )
    except DataError:
        raise WrongDateFormatException

    if time_spent is None:
        raise TimeSpentNotFoundException

    task = Task.get(task_id)
    project_id = str(task.project_id)
    time_spent.duration = 0
    time_spent.delete()
    events.emit(
        "time-spent:delete",
        {"time_spent_id": str(time_spent.id)},
        project_id=project_id,
    )

    task.duration = sum(
        time_spent.duration
        for time_spent in TimeSpent.get_all_by(task_id=task_id)
    )
    task.save()
    clear_task_cache(task_id)
    events.emit("task:update", {"task_id": task_id}, project_id=project_id)

    return time_spent.serialize()


def is_finished(task, data):
    """
    Return True if task status is set to feedback request.
    """
    if "task_status_id" in data:
        task_status = get_task_status_raw(task.task_status_id)
        new_task_status = get_task_status_raw(data["task_status_id"])
        return (
            new_task_status.id != task_status.id
            and new_task_status.is_feedback_request
        )
    else:
        return False


def is_done(task, data):
    """
    Return True if task status is set to done.
    """
    if "task_status_id" in data:
        task_status = get_task_status_raw(task.task_status_id)
        new_task_status = get_task_status_raw(data["task_status_id"])
        return new_task_status.id != task_status.id and new_task_status.is_done
    else:
        return False


def clear_assignation(task_id, person_id=None):
    """
    Clear task assignation and emit a *task:unassign* event.
    """
    task = get_task_raw(task_id)
    project_id = str(task.project_id)

    removed_assignments = []
    if person_id is None:
        removed_assignments = [person.serialize() for person in task.assignees]
        task.update({"assignees": []})
    else:
        assignees = [
            person for person in task.assignees if str(person.id) != person_id
        ]
        task.update({"assignees": assignees})
        removed_assignments = [{"id": person_id}]

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
    task_id, person, comment, preview_path={}, change_status=True
):
    """
    Deprecated
    Change the task status to "waiting for approval" if it is not already the
    case. It emits a *task:to-review* event.
    """
    task = get_task_raw(task_id)
    to_review_status = get_to_review_status()
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


def add_preview_file_to_comment(comment_id, person_id, task_id, revision=0):
    """
    Add a preview to comment preview list. Auto set the revision field
    (add 1 if it's a new preview, keep the preview revision in other cases).
    """
    comment = get_comment_raw(comment_id)
    news = News.get_by(comment_id=comment_id)
    task = Task.get(comment.object_id)
    project_id = str(task.project_id)
    position = 1
    if revision == 0 and len(comment.previews) == 0:
        revision = get_next_preview_revision(task_id)
    elif revision == 0:
        revision = comment.previews[0].revision
        position = get_next_position(task_id, revision)
    else:
        position = get_next_position(task_id, revision)
    preview_file = files_service.create_preview_file_raw(
        str(uuid.uuid4())[:13], revision, task_id, person_id, position=position
    )
    events.emit(
        "preview-file:new",
        {
            "preview_file_id": preview_file.id,
            "comment_id": comment_id,
        },
        project_id=project_id,
    )
    comment.previews.append(preview_file)
    comment.save()
    if news is not None:
        news.update({"preview_file_id": preview_file.id})
    events.emit(
        "comment:update", {"comment_id": comment.id}, project_id=project_id
    )
    return preview_file.serialize()


def update_preview_file_info(preview_file):
    entity = None
    task = get_task_raw(preview_file["task_id"])
    if preview_file["position"] == 1:
        task.update({"last_preview_file_id": preview_file["id"]})
        clear_task_cache(str(task.id))
        project = projects_service.get_project(task.project_id)

        if project["is_set_preview_automated"]:
            entity_id = str(task.entity_id)
            entity = entities_service.update_entity_preview(
                entity_id,
                preview_file["id"],
            )
            assets_service.clear_asset_cache(entity_id)
            edits_service.clear_edit_cache(entity_id)
            shots_service.clear_shot_cache(entity_id)
            shots_service.clear_episode_cache(entity_id)
            shots_service.clear_sequence_cache(entity_id)
    return entity


def get_comments_for_project(project_id, page=0):
    """
    Return all comments for given project.
    """
    query = (
        Comment.query.join(Task, Task.id == Comment.object_id)
        .filter(Task.project_id == project_id)
        .order_by(Comment.updated_at.desc())
    )
    return query_utils.get_paginated_results(query, page, relations=True)


def get_time_spents_for_project(project_id, page=0):
    """
    Return all time spents for given project.
    """
    query = TimeSpent.query.join(Task).filter(Task.project_id == project_id)
    return query_utils.get_paginated_results(query, page)


def get_tasks_for_project(
    project_id, page=0, task_type_id=None, episode_id=None
):
    """
    Return all tasks for given project.
    """
    query = Task.query.filter(Task.project_id == project_id).order_by(
        Task.updated_at.desc()
    )
    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)
    if episode_id is not None:
        Sequence = aliased(Entity, name="sequence")
        query = (
            query.join(Entity, Entity.id == Task.entity_id)
            .join(Sequence, Sequence.id == Entity.parent_id)
            .filter(Sequence.parent_id == episode_id)
        )

        if permissions.has_vendor_permissions():
            query = query.filter(user_service.build_assignee_filter())
        elif not permissions.has_admin_permissions():
            query = query.join(Project).filter(
                user_service.build_related_projects_filter()
            )
        return query

    return query_utils.get_paginated_results(query, page, relations=True)


def get_full_task(task_id, user_id):
    task = get_task_with_relations(task_id)
    task_type = get_task_type(task["task_type_id"])
    project = projects_service.get_project(task["project_id"])
    task_status = get_task_status(task["task_status_id"])
    entity = entities_service.get_entity(task["entity_id"])
    entity_type = entities_service.get_entity_type(entity["entity_type_id"])
    is_subscribed = notifications_service.is_person_subscribed(
        user_id, task_id
    )
    assignees = [
        persons_service.get_person(assignee_id)
        for assignee_id in task["assignees"]
    ]

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
    for task in Task.get_all_by(project_id=project_id):
        reset_task_data(str(task.id))


def reset_task_data(task_id):
    clear_task_cache(task_id)
    task = Task.get(task_id)
    retake_count = 0
    real_start_date = None
    last_comment_date = None
    end_date = None
    done_date = None
    entity = entities_service.get_entity(task.entity_id)
    task_status_id = get_default_status(
        for_concept=entity["entity_type_id"]
        == concepts_service.get_concept_type()["id"]
    )["id"]
    comments = (
        Comment.query.join(TaskStatus)
        .filter(Comment.object_id == task_id)
        .order_by(Comment.created_at)
        .add_columns(
            TaskStatus.is_retake,
            TaskStatus.is_feedback_request,
            TaskStatus.is_done,
            TaskStatus.short_name,
        )
        .all()
    )

    previous_is_retake = False
    for (
        comment,
        task_status_is_retake,
        task_status_is_feedback_request,
        task_status_is_done,
        task_status_short_name,
    ) in comments:
        if task_status_is_retake and not previous_is_retake:
            retake_count += 1
        previous_is_retake = task_status_is_retake

        if task_status_short_name.lower() == "wip" and real_start_date is None:
            real_start_date = comment.created_at

        if task_status_is_feedback_request:
            end_date = comment.created_at

        print("ok", task_status_is_done)
        if task_status_is_done:
            done_date = comment.created_at
            print(done_date)

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
    project_id = str(task.project_id)
    events.emit("task:update", {"task_id": task.id}, project_id)
    return task.serialize(relations=True)


def get_persons_tasks_dates():
    """
    For schedule usages, for each active person, it returns the first start
    date of all tasks of assigned to this person and the last end date.
    """
    project_ids = projects_service.open_project_ids()
    query = (
        Task.query.with_entities(
            Person.id, func.min(Task.start_date), func.max(Task.due_date)
        )
        .filter(Person.active)
        .filter(Task.project_id.in_(project_ids))
        .group_by(Person.id)
        .join(Task.assignees)
    )
    return [
        {
            "person_id": str(person_id),
            "min_date": str(min_date),
            "max_date": str(max_date),
        }
        for (person_id, min_date, max_date) in query.all()
    ]


def get_open_tasks(
    task_type_id=None,
    task_status_id=None,
    project_id=None,
    person_id=None,
    start_date=None,
    due_date=None,
    priority=None,
    order_by=None,
    limit=200,
    page=None,
):
    """
    Return all tasks matching given filters from open projects.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    from zou.app import db

    query_stats = (
        db.session.query(
            func.count().label("amount"),
            func.sum(Task.duration).label("total_duration"),
            func.sum(Task.estimation).label("total_estimation"),
        )
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
    )
    query = (
        Task.query.join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .outerjoin(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .add_columns(
            Project.name,
            Project.has_avatar,
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            EntityType.name,
            Entity.canceled,
            Entity.parent_id,
            Entity.source_id,
            Sequence.name,
            Episode.id,
            Episode.name,
            TaskType.name,
            TaskType.for_entity,
            TaskStatus.name,
            TaskType.color,
            TaskStatus.color,
            TaskStatus.short_name,
        )
    ).order_by(
        Project.name,
        Episode.name,
        Sequence.name,
        EntityType.name,
        Entity.name,
        TaskType.name,
    )

    if project_id is not None and user_service.check_project_access(
        project_id
    ):
        query = query.filter(Project.id == project_id)
        query_stats = query_stats.filter(Project.id == project_id)
    else:
        if permissions.has_admin_permissions():
            query = query.filter(ProjectStatus.name == "Open")
            query_stats = query_stats.filter(ProjectStatus.name == "Open")
        else:
            query = query.filter(user_service.build_related_projects_filter())
            query_stats = query_stats.filter(
                user_service.build_related_projects_filter()
            )

    if task_type_id is not None:
        query = query.filter(TaskType.id == task_type_id)
        query_stats = query_stats.filter(TaskType.id == task_type_id)
    else:
        query = query.filter(TaskType.for_entity != "Concept")

    if task_status_id is not None:
        query = query.filter(TaskStatus.id == task_status_id)
        query_stats = query_stats.filter(TaskStatus.id == task_status_id)

    if person_id is not None:
        if person_id == "unassigned":
            query = query.filter(Task.assignees == None)
            query_stats = query_stats.filter(Task.assignees == None)
        else:
            query = query.filter(Task.assignees.any(id=person_id))
            query_stats = query_stats.filter(Task.assignees.any(id=person_id))

    if start_date is not None:
        query = query.filter(Task.start_date >= start_date)
        query_stats = query_stats.filter(Task.start_date >= start_date)

    if due_date is not None:
        query = query.filter(Task.due_date <= due_date)
        query_stats = query_stats.filter(Task.due_date <= due_date)

    if priority is not None:
        query = query.filter(TaskType.priority == priority)
        query_stats = query_stats.filter(TaskType.priority == priority)

    if page is not None and int(page) > 0:
        query = query.offset((page - 1) * limit)

    if order_by is not None:
        query = query.order_by(order_by)

    query_stats_status = query_stats.group_by(TaskStatus.id).add_columns(
        TaskStatus.id
    )

    tasks = []

    for (
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
    ) in query.limit(limit).all():
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

        task_dict = get_task_with_relations(str(task.id))
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
                "estimation": task.estimation,
                "duration": task.duration,
                "start_date": fields.serialize_value(task.start_date),
                "due_date": fields.serialize_value(task.due_date),
                "done_date": fields.serialize_value(task.done_date),
                "type_name": task_type_name,
                "task_type_for_entity": task_type_for_entity,
                "status_name": task_status_name,
                "type_color": task_type_color,
                "status_color": task_status_color,
                "status_short_name": task_status_short_name,
            }
        )
        tasks.append(task_dict)

    result = {
        "data": [],
        "stats": {
            "total_duration": 0,
            "total_estimation": 0,
            "total": 0,
            "status": [],
        },
        "limit": limit,
        "is_more": False,
        "page": page or 1,
    }

    if len(tasks) > 0:
        count = query.count()
        stats = query_stats.one()
        stats_status = query_stats_status.all()
        statuses_stats = [
            {"task_status_id": stat.id, "amount": stat.amount}
            for stat in stats_status
        ]

        result = {
            "data": tasks,
            "stats": {
                "total_duration": stats.total_duration,
                "total_estimation": stats.total_estimation,
                "total": count,
                "status": statuses_stats,
            },
            "limit": limit,
            "is_more": len(tasks) == limit,
            "page": page or 1,
        }
    return result


def get_open_tasks_stats():
    """
    Return the amount of tasks, done tasks, estimation, and duration for each
    status in open projects. Aggregate the amounts for each project.
    """
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    from zou.app import db

    query_stats = (
        db.session.query(
            func.count().label("amount"),
            func.count(case({TaskStatus.is_done: Task.id})).label(
                "amount_done"
            ),
            func.sum(Task.duration).label("total_duration"),
            func.sum(Task.estimation).label("total_estimation"),
        )
        .join(TaskType, Task.task_type_id == TaskType.id)
        .join(TaskStatus, Task.task_status_id == TaskStatus.id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .join(Project, Project.id == Task.project_id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .filter(TaskType.for_entity != "Concept")
        .group_by(Project.id, TaskType.id, TaskStatus.id)
        .add_columns(
            Project.id.label("project_id"),
            TaskType.id.label("task_type_id"),
            TaskStatus.id.label("task_status_id"),
        )
    )

    if permissions.has_admin_permissions():
        query_stats = query_stats.filter(ProjectStatus.name == "Open")
    else:
        query_stats = query_stats.filter(
            user_service.build_related_projects_filter()
        )

    stats_status = query_stats.all()

    statuses_stats = [
        {
            "task_status_id": stat.task_status_id,
            "task_type_id": stat.task_type_id,
            "project_id": stat.project_id,
            "amount": stat.amount,
            "amount_done": stat.amount_done,
            "total_duration": stat.total_duration,
            "total_estimation": stat.total_estimation,
        }
        for stat in stats_status
    ]

    stats_map = {}
    for stat in statuses_stats:
        project_id = stat["project_id"]
        if project_id not in stats_map:
            stats_map[project_id] = {
                "amount": 0,
                "amount_done": 0,
                "total_duration": 0,
                "total_estimation": 0,
                "task_types": [],
            }
        project_stats = stats_map[project_id]
        project_stats["amount"] += stat["amount"]
        project_stats["amount_done"] += stat["amount_done"]
        project_stats["total_duration"] += stat["total_duration"]
        project_stats["total_estimation"] += stat["total_estimation"]
        project_stats["task_types"].append(stat)

    return stats_map
