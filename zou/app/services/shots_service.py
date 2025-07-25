from datetime import timedelta
from operator import itemgetter
from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy import func, or_

from zou.app.utils import (
    cache,
    date_helpers,
    events,
    fields,
    query as query_utils,
)

from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityVersion,
    EntityConceptLink,
)
from zou.app.models.person import Person
from zou.app.models.project import Project
from zou.app.models.preview_file import PreviewFile
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.time_spent import TimeSpent

from zou.app.services import (
    deletion_service,
    entities_service,
    persons_service,
    projects_service,
    notifications_service,
    names_service,
    user_service,
    index_service,
    concepts_service,
)
from zou.app.services.exception import (
    EpisodeNotFoundException,
    ModelWithRelationsDeletionException,
    SequenceNotFoundException,
    SceneNotFoundException,
    ShotNotFoundException,
    WrongIdFormatException,
)


def clear_shot_cache(shot_id):
    cache.cache.delete_memoized(get_shot, shot_id)
    cache.cache.delete_memoized(get_shot, shot_id, True)
    cache.cache.delete_memoized(get_full_shot, shot_id)


def clear_sequence_cache(sequence_id):
    cache.cache.delete_memoized(get_sequence, sequence_id)
    cache.cache.delete_memoized(get_full_sequence, sequence_id)


def clear_episode_cache(episode_id):
    cache.cache.delete_memoized(get_episode, episode_id)
    cache.cache.delete_memoized(get_episode_by_name)


@cache.memoize_function(1200)
def get_episode_type():
    return entities_service.get_temporal_entity_type_by_name("Episode")


@cache.memoize_function(1200)
def get_edit_type():
    return entities_service.get_temporal_entity_type_by_name("Edit")


@cache.memoize_function(1200)
def get_sequence_type():
    return entities_service.get_temporal_entity_type_by_name("Sequence")


@cache.memoize_function(1200)
def get_shot_type():
    return entities_service.get_temporal_entity_type_by_name("Shot")


@cache.memoize_function(1200)
def get_scene_type():
    return entities_service.get_temporal_entity_type_by_name("Scene")


@cache.memoize_function(1200)
def get_camera_type():
    return entities_service.get_entity_type_by_name("Camera")


def get_episodes(criterions={}):
    """
    Get all episodes for given criterions.
    """
    episode_type = get_episode_type()
    criterions["entity_type_id"] = episode_type["id"]
    query = Entity.query.order_by(Entity.name)
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    try:
        episodes = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException
    return Entity.serialize_list(episodes, obj_type="Episode")


def get_sequences(criterions={}):
    """
    Get all sequences for given criterions.
    """
    sequence_type = get_sequence_type()
    criterions["entity_type_id"] = sequence_type["id"]
    query = Entity.query.order_by(Entity.name)
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    try:
        sequences = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException
    return Entity.serialize_list(sequences, obj_type="Sequence")


def get_shots(criterions={}):
    """
    Get all shots for given criterions.
    """
    shot_type = get_shot_type()
    criterions["entity_type_id"] = shot_type["id"]
    Sequence = aliased(Entity, name="sequence")
    is_only_assignation = "assigned_to" in criterions
    if is_only_assignation:
        del criterions["assigned_to"]

    query = Entity.query
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    query = (
        query.join(Project, Project.id == Entity.project_id)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .add_columns(Project.name)
        .add_columns(Sequence.name)
        .order_by(Entity.name)
    )

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(user_service.build_assignee_filter())

    try:
        data = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException

    shots = []
    for shot_model, project_name, sequence_name in data:
        shot = shot_model.serialize(obj_type="Shot")
        shot["project_name"] = project_name
        shot["sequence_name"] = sequence_name
        shots.append(shot)

    return shots


def get_scenes(criterions={}):
    """
    Get all scenes for given criterions.
    """
    scene_type = get_scene_type()
    criterions["entity_type_id"] = scene_type["id"]
    Sequence = aliased(Entity, name="sequence")

    is_only_assignation = "assigned_to" in criterions
    if is_only_assignation:
        del criterions["assigned_to"]

    query = Entity.query
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    query = (
        query.join(Project, Entity.project_id == Project.id)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .add_columns(Project.name)
        .add_columns(Sequence.name)
    )

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(user_service.build_assignee_filter())

    try:
        data = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException

    scenes = []
    for scene_model, project_name, sequence_name in data:
        scene = scene_model.serialize(obj_type="Scene")
        scene["project_name"] = project_name
        scene["sequence_name"] = sequence_name
        scenes.append(scene)

    return scenes


def get_episode_map(criterions={}):
    """
    Returns a dict where keys are episode_id and values are episodes.
    """
    episodes = get_episodes(criterions)
    episode_map = {}
    for episode in episodes:
        episode_map[episode["id"]] = episode
    return episode_map


def get_shots_and_tasks(criterions={}):
    """
    Get all shots for given criterions with related tasks for each shot.
    """
    shot_type = get_shot_type()
    shot_map = {}
    task_map = {}
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), get_shot_type()["id"]
    )

    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    query = (
        Entity.query.join(Project, Project.id == Entity.project_id)
        .join(Sequence, Sequence.id == Entity.parent_id)
        .outerjoin(Episode, Episode.id == Sequence.parent_id)
        .outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(TaskPersonLink)
        .add_columns(
            Episode.name,
            Episode.id,
            Sequence.name,
            Sequence.id,
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
            Task.done_date,
            Task.last_comment_date,
            Task.last_preview_file_id,
            Task.nb_assets_ready,
            Task.difficulty,
            Task.nb_drawings,
            TaskPersonLink.person_id,
            Project.id,
            Project.name,
        )
        .filter(Entity.entity_type_id == shot_type["id"])
    )
    if "id" in criterions:
        query = query.filter(Entity.id == criterions["id"])

    if "project_id" in criterions:
        query = query.filter(Entity.project_id == criterions["project_id"])

    if "episode_id" in criterions and criterions["episode_id"] != "all":
        query = query.filter(Sequence.parent_id == criterions["episode_id"])

    if "assigned_to" in criterions:
        query = query.filter(user_service.build_assignee_filter())
        del criterions["assigned_to"]

    query_result = query.all()

    if "vendor_departments" in criterions:
        not_allowed_descriptors_field_names = (
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                "Shot",
                criterions["vendor_departments"],
                set(shot[0].project_id for shot in query_result),
            )
        )

    for (
        shot,
        episode_name,
        episode_id,
        sequence_name,
        sequence_id,
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
        task_done_date,
        task_last_comment_date,
        task_last_preview_file_id,
        task_nb_assets_ready,
        task_difficulty,
        task_nb_drawings,
        person_id,
        project_id,
        project_name,
    ) in query_result:
        shot_id = str(shot.id)

        if shot_id not in shot_map:
            data = fields.serialize_value(shot.data or {})
            if "vendor_departments" in criterions:
                data = (
                    entities_service.remove_not_allowed_fields_from_metadata(
                        not_allowed_descriptors_field_names[shot.project_id],
                        data,
                    )
                )

            shot_map[shot_id] = fields.serialize_dict(
                {
                    "canceled": shot.canceled,
                    "data": data,
                    "description": shot.description,
                    "entity_type_id": shot.entity_type_id,
                    "episode_id": episode_id,
                    "episode_name": episode_name or "",
                    "fps": data.get("fps", None),
                    "frame_in": data.get("frame_in", None),
                    "frame_out": data.get("frame_out", None),
                    "id": shot.id,
                    "name": shot.name,
                    "nb_frames": shot.nb_frames,
                    "parent_id": shot.parent_id,
                    "preview_file_id": shot.preview_file_id or None,
                    "project_id": project_id,
                    "project_name": project_name,
                    "sequence_id": sequence_id,
                    "sequence_name": sequence_name,
                    "source_id": shot.source_id,
                    "nb_entities_out": shot.nb_entities_out,
                    "is_casting_standby": shot.is_casting_standby,
                    "tasks": [],
                    "type": "Shot",
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
                        "end_date": task_end_date,
                        "done_date": task_done_date,
                        "entity_id": shot_id,
                        "estimation": task_estimation,
                        "is_subscribed": subscription_map.get(task_id, False),
                        "last_comment_date": task_last_comment_date,
                        "last_preview_file_id": task_last_preview_file_id,
                        "nb_assets_ready": task_nb_assets_ready,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "difficulty": task_difficulty,
                        "nb_drawings": task_nb_drawings,
                        "task_status_id": task_status_id,
                        "task_type_id": task_type_id,
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                shot_dict = shot_map[shot_id]
                shot_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(shot_map.values())


def get_shot_raw(shot_id):
    """
    Return given shot as an active record.
    """
    shot_type = get_shot_type()
    try:
        shot = Entity.get_by(entity_type_id=shot_type["id"], id=shot_id)
    except StatementError:
        raise ShotNotFoundException

    if shot is None:
        raise ShotNotFoundException

    return shot


@cache.memoize_function(120)
def get_shot(shot_id, relations=False):
    """
    Return given shot as a dictionary.
    """
    return get_shot_raw(shot_id).serialize(
        obj_type="Shot", relations=relations
    )


@cache.memoize_function(120)
def get_full_shot(shot_id):
    """
    Return given shot as a dictionary with extra data like project and
    sequence names.
    """
    shots = get_shots_and_tasks({"id": shot_id})
    if len(shots) > 0:
        shot = shots[0]
        shot.update(get_shot(shot_id, relations=True))
        return shot
    else:
        raise ShotNotFoundException


def get_scene_raw(scene_id):
    """
    Return given scene as an active record.
    """
    scene_type = get_scene_type()
    try:
        scene = Entity.get_by(entity_type_id=scene_type["id"], id=scene_id)
    except StatementError:
        raise SceneNotFoundException

    if scene is None:
        raise SceneNotFoundException

    return scene


def get_scene(scene_id):
    """
    Return given scene as a dictionary.
    """
    return get_scene_raw(scene_id).serialize(obj_type="Scene")


def get_full_scene(scene_id):
    """
    Return given scene as a dictionary with extra data like project and sequence
    names.
    """
    scene = get_scene(scene_id)
    project = projects_service.get_project(scene["project_id"])
    sequence = get_sequence(scene["parent_id"])
    scene["project_name"] = project["name"]
    scene["sequence_id"] = sequence["id"]
    scene["sequence_name"] = sequence["name"]
    if sequence["parent_id"] is not None:
        episode = get_episode(sequence["parent_id"])
        scene["episode_id"] = episode["id"]
        scene["episode_name"] = episode["name"]

    return scene


def get_sequence_raw(sequence_id):
    """
    Return given sequence as an active record.
    """
    sequence_type = get_sequence_type()
    try:
        sequence = Entity.get_by(
            entity_type_id=sequence_type["id"], id=sequence_id
        )
    except StatementError:
        raise SequenceNotFoundException

    if sequence is None:
        raise SequenceNotFoundException

    return sequence


@cache.memoize_function(120)
def get_sequence(sequence_id):
    """
    Return given sequence as a dictionary.
    """
    return get_sequence_raw(sequence_id).serialize(obj_type="Sequence")


@cache.memoize_function(120)
def get_full_sequence(sequence_id):
    """
    Return given sequence as a dictionary with extra data like project name.
    """
    sequence = get_sequence(sequence_id)
    project = projects_service.get_project(sequence["project_id"])
    sequence["project_name"] = project["name"]

    if sequence["parent_id"] is not None:
        episode = get_episode(sequence["parent_id"])
        sequence["episode_id"] = episode["id"]
        sequence["episode_name"] = episode["name"]

    return sequence


def get_sequence_from_shot(shot):
    """
    Return parent sequence of given shot.
    """
    try:
        sequence = Entity.get(shot["parent_id"])
    except Exception:
        raise SequenceNotFoundException("Wrong parent_id for given shot.")
    return sequence.serialize(obj_type="Sequence")


def get_episode_raw(episode_id):
    """
    Return given episode as an active record.
    """
    episode_type = get_episode_type()
    if episode_type is None:
        episode_type = get_episode_type()

    try:
        episode = Entity.get_by(
            entity_type_id=episode_type["id"], id=episode_id
        )
    except StatementError:
        raise EpisodeNotFoundException

    if episode is None:
        raise EpisodeNotFoundException
    return episode


@cache.memoize_function(120)
def get_episode(episode_id):
    """
    Return given episode as a dictionary.
    """
    return get_episode_raw(episode_id).serialize(obj_type="Episode")


@cache.memoize_function(120)
def get_episode_by_name(project_id, episode_name):
    """
    Get episode matching given name project_id. Raises an exception if episode
    is not found.
    """
    episode_type_id = get_episode_type()["id"]
    episode = (
        Entity.query.filter(Entity.entity_type_id == episode_type_id)
        .filter(Entity.project_id == project_id)
        .filter(Entity.name.ilike(episode_name))
        .first()
    )

    if episode is None:
        raise EpisodeNotFoundException()

    return episode.serialize(obj_type="Episode")


def get_full_episode(episode_id):
    """
    Return given episode as a dictionary with extra data like project name.
    """
    episode = get_episode(episode_id)
    project = projects_service.get_project(episode["project_id"])
    episode["project_name"] = project["name"]
    return episode


def get_episode_from_sequence(sequence):
    """
    Return parent episode of given sequence.
    """
    try:
        episode = Entity.get(sequence["parent_id"])
    except Exception:
        raise EpisodeNotFoundException("Wrong parent_id for given sequence.")
    return episode.serialize(obj_type="Episode")


def get_shot_by_shotgun_id(shotgun_id):
    """
    Retrieves a shot identifed by its shotgun ID (stored during import).
    """
    shot_type = get_shot_type()
    shot = Entity.get_by(entity_type_id=shot_type["id"], shotgun_id=shotgun_id)
    if shot is None:
        raise ShotNotFoundException

    return shot.serialize(obj_type="Shot")


def get_scene_by_shotgun_id(shotgun_id):
    """
    Retrieves a scene identifed by its shotgun ID (stored during import).
    """
    scene_type = get_scene_type()
    scene = Entity.get_by(
        entity_type_id=scene_type["id"], shotgun_id=shotgun_id
    )
    if scene is None:
        raise SceneNotFoundException

    return scene.serialize(obj_type="Scene")


def get_sequence_by_shotgun_id(shotgun_id):
    """
    Retrieves a sequence identifed by its shotgun ID (stored during import).
    """
    sequence_type = get_sequence_type()
    sequence = Entity.get_by(
        entity_type_id=sequence_type["id"], shotgun_id=shotgun_id
    )
    if sequence is None:
        raise SequenceNotFoundException

    return sequence.serialize(obj_type="Sequence")


def get_episode_by_shotgun_id(shotgun_id):
    """
    Retrieves an episode identifed by its shotgun ID (stored during import).
    """
    episode_type = get_episode_type()
    episode = Entity.get_by(
        entity_type_id=episode_type["id"], shotgun_id=shotgun_id
    )
    if episode is None:
        raise EpisodeNotFoundException

    return episode.serialize(obj_type="Episode")


def is_shot(entity):
    """
    Returns True if given entity has 'Shot' as entity type
    """
    shot_type = get_shot_type()
    return str(entity["entity_type_id"]) == shot_type["id"]


def is_scene(entity):
    """
    Returns True if given entity has 'Scene' as entity type
    """
    scene_type = get_scene_type()
    return str(entity["entity_type_id"]) == scene_type["id"]


def is_sequence(entity):
    """
    Returns True if given entity has 'Sequence' as entity type
    """
    sequence_type = get_sequence_type()
    return str(entity["entity_type_id"]) == sequence_type["id"]


def is_edit(entity):
    """
    Returns True if given entity has 'Edit' as entity type
    """
    edit_type = get_edit_type()
    return str(entity["entity_type_id"]) == edit_type["id"]


def is_episode(entity):
    """
    Returns True if given entity has 'Episode' as entity type
    """
    episode_type = get_episode_type()
    return str(entity["entity_type_id"]) == episode_type["id"]


def get_or_create_first_episode(project_id, created_by=None):
    """
    Get the first episode of the production.
    """
    episode = (
        Entity.query.filter_by(project_id=project_id)
        .order_by(Entity.name)
        .first()
    )
    if episode is not None:
        return episode.serialize()
    else:
        return create_episode(
            project_id, "running", "E01", created_by=created_by
        )


def get_episodes_for_project(project_id, only_assigned=False):
    """
    Retrieve all episodes related to given project.
    """
    if only_assigned:
        Sequence = aliased(Entity, name="sequence")
        Shot = aliased(Entity, name="shot")
        Asset = aliased(Entity, name="asset")
        query = (
            Entity.query.join(Sequence, Entity.id == Sequence.parent_id)
            .join(Shot, Sequence.id == Shot.parent_id)
            .join(Task, Shot.id == Task.entity_id)
            .filter(Entity.project_id == project_id)
            .filter(user_service.build_assignee_filter())
        )
        shot_episodes = fields.serialize_models(query.all())
        shot_episode_ids = {episode["id"]: True for episode in shot_episodes}
        query = (
            Entity.query.join(Asset, Entity.id == Asset.source_id)
            .join(Task, Asset.id == Task.entity_id)
            .filter(Entity.project_id == project_id)
            .filter(user_service.build_assignee_filter())
        )
        asset_episodes = fields.serialize_models(query.all())
        result = shot_episodes
        for episode in asset_episodes:
            if episode["id"] not in shot_episode_ids:
                result.append(episode)
        return result
    else:
        return entities_service.get_entities_for_project(
            project_id, get_episode_type()["id"], "Episode"
        )


def get_sequences_for_project(project_id, only_assigned=False):
    """
    Retrieve all sequences related to given project.
    """
    if only_assigned:
        Shot = aliased(Entity, name="shot")
        query = (
            Entity.query.join(Shot, Entity.id == Shot.parent_id)
            .join(Task, Shot.id == Task.entity_id)
            .filter(Entity.project_id == project_id)
            .filter(user_service.build_assignee_filter())
        )
        return fields.serialize_models(query.all())
    else:
        return entities_service.get_entities_for_project(
            project_id, get_sequence_type()["id"], "Sequence"
        )


def get_sequences_for_episode(episode_id, only_assigned=False):
    """
    Retrieve all sequences related to given episode.
    """
    if only_assigned:
        Shot = aliased(Entity, name="shot")
        query = (
            Entity.query.join(Shot, Entity.id == Shot.parent_id)
            .join(Task, Shot.id == Task.entity_id)
            .filter(Entity.parent_id == episode_id)
            .filter(user_service.build_assignee_filter())
        )
        return fields.serialize_models(query.all())
    else:
        return get_sequences({"parent_id": episode_id})


def get_shots_for_project(project_id, only_assigned=False):
    """
    Retrieve all shots related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id, get_shot_type()["id"], "Shot", only_assigned=only_assigned
    )


def get_shots_for_episode(episode_id, relations=False):
    """
    Get all shots for given episode.
    """
    Sequence = aliased(Entity, name="sequence")
    shot_type_id = get_shot_type()["id"]
    result = (
        Entity.query.filter(Entity.entity_type_id == shot_type_id)
        .filter(Sequence.parent_id == episode_id)
        .join(Sequence, Entity.parent_id == Sequence.id)
    ).all()
    return Entity.serialize_list(result, "Shot", relations=relations)


def get_scenes_for_project(project_id, only_assigned=False):
    """
    Retrieve all scenes related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id,
        get_scene_type()["id"],
        "Scene",
        only_assigned=only_assigned,
    )


def get_scenes_for_sequence(sequence_id):
    """
    Retrieve all scenes children of given sequence.
    """
    get_sequence(sequence_id)
    scene_type_id = get_scene_type()["id"]
    result = (
        Entity.query.filter(Entity.entity_type_id == scene_type_id)
        .filter(Entity.parent_id == sequence_id)
        .order_by(Entity.name)
        .all()
    )
    return Entity.serialize_list(result, "Scene")


def remove_shot(shot_id, force=False):
    """
    Remove given shot from database. If it has tasks linked to it, it marks
    the shot as canceled. Deletion can be forced.
    """
    shot = get_shot_raw(shot_id)
    is_tasks_related = Task.query.filter_by(entity_id=shot_id).count() > 0

    if is_tasks_related and not force:
        shot.update({"canceled": True})
        clear_shot_cache(shot_id)
        events.emit(
            "shot:update",
            {"shot_id": shot_id},
            project_id=str(shot.project_id),
        )
    else:
        from zou.app.services import tasks_service

        tasks = Task.query.filter_by(entity_id=shot_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))

        EntityVersion.delete_all_by(entity_id=shot_id)
        Subscription.delete_all_by(entity_id=shot_id)
        EntityLink.delete_all_by(entity_in_id=shot_id)
        EntityLink.delete_all_by(entity_out_id=shot_id)
        EntityConceptLink.delete_all_by(entity_in_id=shot_id)
        EntityConceptLink.delete_all_by(entity_out_id=shot_id)

        shot.delete()
        events.emit(
            "shot:delete",
            {"shot_id": shot_id},
            project_id=str(shot.project_id),
        )
        index_service.remove_shot_index(shot_id)
        clear_shot_cache(shot_id)

    deleted_shot = shot.serialize(obj_type="Shot")
    return deleted_shot


def remove_scene(scene_id):
    """
    Remove given scene from database. If it has tasks linked to it, it marks
    the scene as canceled.
    """
    scene = get_scene_raw(scene_id)
    try:
        scene.delete()
    except IntegrityError:
        scene.update({"canceled": True})
    deleted_scene = scene.serialize(obj_type="Scene")
    events.emit(
        "scene:delete",
        {"scene_id": scene_id},
        project_id=str(scene.project_id),
    )
    return deleted_scene


def remove_sequence(sequence_id, force=False):
    """
    Remove a sequence and all related shots.
    """
    sequence = get_sequence_raw(sequence_id)
    if force:
        from zou.app.services import tasks_service

        for shot in Entity.get_all_by(parent_id=sequence_id):
            remove_shot(shot.id, force=True)
        Subscription.delete_all_by(entity_id=sequence_id)
        ScheduleItem.delete_all_by(object_id=sequence_id)

        tasks = Task.query.filter_by(entity_id=sequence_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))
        Subscription.delete_all_by(entity_id=sequence_id)
    try:
        sequence.delete()
        events.emit(
            "sequence:delete",
            {"sequence_id": sequence_id},
            project_id=str(sequence.project_id),
        )
    except IntegrityError:
        raise ModelWithRelationsDeletionException(
            "Some data are still linked to this sequence."
        )
    clear_sequence_cache(sequence_id)
    return sequence.serialize(obj_type="Sequence")


def create_episode(
    project_id,
    name,
    status="running",
    description="",
    data={},
    created_by=None,
):
    """
    Create episode for given project.
    """
    episode_type = get_episode_type()
    episode = Entity.get_by(
        entity_type_id=episode_type["id"], project_id=project_id, name=name
    )
    if status not in ["running", "complete", "standby", "canceled"]:
        status = "running"
    if episode is None:
        episode = Entity.create(
            entity_type_id=episode_type["id"],
            project_id=project_id,
            name=name,
            status=status,
            description=description,
            data=data,
            created_by=created_by,
        )
        events.emit(
            "episode:new", {"episode_id": episode.id}, project_id=project_id
        )
    return episode.serialize(obj_type="Episode")


def create_sequence(
    project_id, episode_id, name, description="", data={}, created_by=None
):
    """
    Create sequence for given project and episode.
    """
    sequence_type = get_sequence_type()

    if episode_id is not None:
        get_episode(episode_id)  # raises EpisodeNotFound if it fails.

    sequence = Entity.get_by(
        entity_type_id=sequence_type["id"],
        parent_id=episode_id,
        project_id=project_id,
        name=name,
    )
    if sequence is None:
        sequence = Entity.create(
            entity_type_id=sequence_type["id"],
            project_id=project_id,
            parent_id=episode_id,
            name=name,
            description=description,
            data=data,
            created_by=created_by,
        )
        events.emit(
            "sequence:new", {"sequence_id": sequence.id}, project_id=project_id
        )
    return sequence.serialize(obj_type="Sequence")


def create_shot(
    project_id,
    sequence_id,
    name,
    data={},
    nb_frames=0,
    description=None,
    created_by=None,
):
    """
    Create shot for given project and sequence.
    """
    shot_type = get_shot_type()

    if sequence_id is not None:
        # raises SequenceNotFound if it fails.
        sequence = get_sequence(sequence_id)

    shot = Entity.get_by(
        entity_type_id=shot_type["id"],
        parent_id=sequence_id,
        project_id=project_id,
        name=name,
    )
    if shot is None:
        shot = Entity.create(
            entity_type_id=shot_type["id"],
            project_id=project_id,
            parent_id=sequence_id,
            name=name,
            data=data,
            nb_frames=nb_frames,
            description=description,
            created_by=created_by,
        )

        index_service.index_shot(shot)
        events.emit(
            "shot:new",
            {
                "shot_id": shot.id,
                "episode_id": sequence["parent_id"],
            },
            project_id=project_id,
        )

    return shot.serialize(obj_type="Shot")


def create_scene(project_id, sequence_id, name, created_by=None):
    """
    Create scene for given project and sequence.
    """
    scene_type = get_scene_type()

    if sequence_id is not None:
        # raises SequenceNotFound if it fails.
        sequence = get_sequence(sequence_id)
        if sequence["project_id"] != project_id:
            raise SequenceNotFoundException

    scene = Entity.get_by(
        entity_type_id=scene_type["id"],
        parent_id=sequence_id,
        project_id=project_id,
        name=name,
    )
    if scene is None:
        scene = Entity.create(
            entity_type_id=scene_type["id"],
            project_id=project_id,
            parent_id=sequence_id,
            name=name,
            data={},
            created_by=created_by,
        )
        events.emit("scene:new", {"scene_id": scene.id}, project_id=project_id)
    return scene.serialize(obj_type="Scene")


def update_shot(shot_id, data_dict):
    """
    Update shot fields matching given id with data from dict given in parameter.
    """
    shot = get_shot_raw(shot_id)
    shot.update(data_dict)

    index_service.remove_shot_index(shot.id)
    index_service.index_shot(shot)
    clear_shot_cache(shot_id)
    events.emit(
        "shot:update", {"shot_id": shot_id}, project_id=str(shot.project_id)
    )

    return shot.serialize()


def get_shot_versions(shot_id):
    """
    Shot metadata changes are versioned. This function returns all versions
    of a given shot.
    """
    versions = (
        EntityVersion.query.filter_by(entity_id=shot_id)
        .order_by(EntityVersion.created_at.desc())
        .all()
    )
    return EntityVersion.serialize_list(versions, obj_type="ShotVersion")


def get_base_entity_type_name(entity_dict):
    type_name = "Asset"
    if is_shot(entity_dict):
        type_name = "Shot"
    elif is_sequence(entity_dict):
        type_name = "Sequence"
    elif is_edit(entity_dict):
        type_name = "Edit"
    elif is_episode(entity_dict):
        type_name = "Episode"
    elif is_scene(entity_dict):
        type_name = "Scene"
    elif concepts_service.is_concept(entity_dict):
        type_name = "Concept"

    return type_name


def get_weighted_quotas(
    project_id,
    task_type_id=None,
    person_id=None,
    studio_id=None,
    feedback=True,
):
    """
    Build quota statistics. It counts the number of frames done for each day.
    A shot is considered done at the first feedback request or at last
    approval.

    If time spent is  filled for it, it weights the result with the frame
    number with the time spents. If there is no time spent, it considers that
    the work was done from the wip date to the feedback date (or approval date).
    It computes the shot count and the number of seconds too.

    If the `feedback` flag is set to True, it uses the feedback date
    (real_end_date), if feedback is set to False, it uses the approval date
    (done_date).
    """
    fps = projects_service.get_project_fps(project_id)
    timezone = user_service.get_timezone()
    shot_type = get_shot_type()
    quotas = {}
    query = (
        Task.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        .add_columns(
            Entity.nb_frames,
            TimeSpent.date,
            TimeSpent.duration,
            TimeSpent.person_id,
        )
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person_id is not None:
        query = query.filter(TimeSpent.person_id == person_id)

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        persons_from_studio = Person.query.filter(
            Person.studio_id == studio_id
        ).all()
        query = query.filter(
            or_(*[Task.assignees.contains(p) for p in persons_from_studio])
        )
    result = query.all()

    for task, nb_frames, date, duration, task_person_id in result:
        task_person_id = str(task_person_id)
        nb_drawings = task.nb_drawings or 0
        nb_frames = nb_frames or 0
        if task.duration > 0:
            nb_frames = round(nb_frames * (duration / task.duration))
            nb_drawings = round(nb_drawings * (duration / task.duration))
            entry_id = str(task_person_id)
            # We get quotas for a specific person split by task types
            if person_id is not None:
                entry_id = str(task.task_type_id)
            for entry in [entry_id, "total"]:
                _add_quota_entry(
                    quotas, entry, date, timezone, nb_frames, nb_drawings, fps
                )

    query = (
        Task.query.filter(Task.project_id == project_id)
        .filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.task_type_id == task_type_id)
        .filter(Task.real_start_date != None)
        .filter(TimeSpent.id == None)
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, Task.id == TimeSpent.task_id)
        .join(Task.assignees)
        .add_columns(Entity.nb_frames, Person.id)
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person_id is not None:
        person = persons_service.get_person_raw(person_id)
        query = query.filter(Task.assignees.contains(person))

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        query = query.filter(
            or_(*[Task.assignees.contains(p) for p in persons_from_studio])
        )
    result = query.all()

    for task, nb_frames, task_person_id in result:
        date = task.done_date
        if feedback:
            date = task.end_date

        business_days = (
            date_helpers.get_business_days(task.real_start_date, date) + 1
        )
        if nb_frames is not None:
            nb_frames = round(nb_frames / business_days) or 0
        else:
            nb_frames = 0

        nb_drawings = task.nb_drawings or 0

        for x in range((date - task.real_start_date).days + 1):
            if date.weekday() < 5:
                entry_id = str(task_person_id)
                # We get quotas for a specific person split by task types
                if person_id is not None:
                    entry_id = str(task.task_type_id)

                for entry in [entry_id, "total"]:
                    _add_quota_entry(
                        quotas,
                        entry,
                        date,
                        timezone,
                        nb_frames,
                        nb_drawings,
                        fps,
                    )
            date = date + timedelta(1)
    return quotas


def get_raw_quotas(
    project_id,
    task_type_id=None,
    person_id=None,
    studio_id=None,
    feedback=True,
):
    """
    Build quota statistics in a raw way. It counts the number of frames done
    for each day. A shot is considered done at the first feedback request (end
    date) or approval date (done_date).

    It considers that all the work was done at the end date.
    It computes the shot count and the number of seconds too.
    """
    fps = projects_service.get_project_fps(project_id)
    timezone = user_service.get_timezone()
    shot_type = get_shot_type()
    quotas = {}
    query = (
        Task.query.filter(Task.project_id == project_id)
        .filter(Entity.entity_type_id == shot_type["id"])
        .join(Entity, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(Task.assignees)
        .add_columns(Entity.nb_frames, Person.id)
    )

    if task_type_id is not None:
        query = query.filter(Task.task_type_id == task_type_id)

    if person_id is not None:
        person = persons_service.get_person_raw(person_id)
        query = query.filter(Task.assignees.contains(person))

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    if studio_id is not None:
        persons_from_studio = Person.query.filter(
            Person.studio_id == studio_id
        ).all()
        query = query.filter(
            or_(*[Task.assignees.contains(p) for p in persons_from_studio])
        )

    result = query.all()

    for task, nb_frames, task_person_id in result:
        date = task.done_date
        if feedback:
            date = task.end_date

        if nb_frames is None:
            nb_frames = 0

        nb_drawings = task.nb_drawings or 0

        entry_id = str(task_person_id)
        if person_id is not None:
            entry_id = str(task.task_type_id)

        for entry in [entry_id, "total"]:
            _add_quota_entry(
                quotas, entry, date, timezone, nb_frames, nb_drawings, fps
            )
    return quotas


def _add_quota_entry(
    quotas, entry_id, date, timezone, nb_frames, nb_drawings, fps
):
    nb_seconds = nb_frames / fps
    date_str = date_helpers.get_simple_string_with_timezone_from_date(
        date, timezone
    )
    year = date_str[:4]
    week = year + "-" + str(date.isocalendar()[1])
    month = date_str[:7]
    if entry_id not in quotas:
        _init_quota_entry(quotas, entry_id)
    _init_quota_date(quotas, entry_id, date_str, week, month)
    quotas[entry_id]["day"]["frames"][date_str] += nb_frames
    quotas[entry_id]["day"]["seconds"][date_str] += nb_seconds
    quotas[entry_id]["day"]["drawings"][date_str] += nb_drawings
    quotas[entry_id]["day"]["count"][date_str] += 1
    quotas[entry_id]["week"]["frames"][week] += nb_frames
    quotas[entry_id]["week"]["seconds"][week] += nb_seconds
    quotas[entry_id]["week"]["drawings"][week] += nb_drawings
    quotas[entry_id]["week"]["count"][week] += 1
    quotas[entry_id]["month"]["frames"][month] += nb_frames
    quotas[entry_id]["month"]["seconds"][month] += nb_seconds
    quotas[entry_id]["month"]["drawings"][month] += nb_drawings
    quotas[entry_id]["month"]["count"][month] += 1
    quotas[entry_id]["year"]["frames"][year] += nb_frames
    quotas[entry_id]["year"]["drawings"][year] += nb_drawings
    quotas[entry_id]["year"]["seconds"][year] += nb_seconds
    quotas[entry_id]["year"]["count"][year] += 1


def _init_quota_date(quotas, entry_id, date_str, week, month):
    year = week[:4]
    if date_str not in quotas[entry_id]["day"]["frames"]:
        quotas[entry_id]["day"]["frames"][date_str] = 0
        quotas[entry_id]["day"]["seconds"][date_str] = 0
        quotas[entry_id]["day"]["count"][date_str] = 0
        quotas[entry_id]["day"]["drawings"][date_str] = 0
        if month not in quotas[entry_id]["day"]["entries"]:
            quotas[entry_id]["day"]["entries"][month] = 0
        quotas[entry_id]["day"]["entries"][month] += 1
    if week not in quotas[entry_id]["week"]["frames"]:
        quotas[entry_id]["week"]["frames"][week] = 0
        quotas[entry_id]["week"]["seconds"][week] = 0
        quotas[entry_id]["week"]["count"][week] = 0
        quotas[entry_id]["week"]["drawings"][week] = 0
        if year not in quotas[entry_id]["week"]["entries"]:
            quotas[entry_id]["week"]["entries"][year] = 0
        quotas[entry_id]["week"]["entries"][year] += 1
    if month not in quotas[entry_id]["month"]["frames"]:
        quotas[entry_id]["month"]["frames"][month] = 0
        quotas[entry_id]["month"]["seconds"][month] = 0
        quotas[entry_id]["month"]["count"][month] = 0
        quotas[entry_id]["month"]["drawings"][month] = 0
        if year not in quotas[entry_id]["month"]["entries"]:
            quotas[entry_id]["month"]["entries"][year] = 0
        quotas[entry_id]["month"]["entries"][year] += 1
    if year not in quotas[entry_id]["year"]["frames"]:
        quotas[entry_id]["year"]["frames"][year] = 0
        quotas[entry_id]["year"]["seconds"][year] = 0
        quotas[entry_id]["year"]["count"][year] = 0
        quotas[entry_id]["year"]["drawings"][year] = 0


def _init_quota_entry(quotas, entry_id):
    quotas[entry_id] = {
        "day": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "week": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "month": {
            "frames": {},
            "seconds": {},
            "count": {},
            "entries": {},
            "drawings": {},
        },
        "year": {"frames": {}, "seconds": {}, "count": {}, "drawings": {}},
    }


def get_month_quota_shots(
    person_id,
    year,
    month,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
):
    """
    Return shots that are included in quota computation for given
    person and month.
    """
    start, end = date_helpers.get_month_interval(year, month)
    start, end = _get_timezoned_interval(start, end)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )


def get_week_quota_shots(
    person_id,
    year,
    week,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
):
    """
    Return shots that are included in quota comptutation for given
    person and week.
    """
    start, end = date_helpers.get_week_interval(year, week)
    start, end = _get_timezoned_interval(start, end)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )


def get_day_quota_shots(
    person_id,
    year,
    month,
    day,
    project_id=None,
    task_type_id=None,
    weighted=True,
    feedback=True,
):
    """
    Return shots that are included in quota comptutation for given
    person and day.
    """
    start, end = date_helpers.get_day_interval(year, month, day)
    if weighted:
        return get_weighted_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )
    else:
        return get_raw_quota_shots_between(
            person_id,
            start,
            end,
            project_id=project_id,
            task_type_id=task_type_id,
            feedback=feedback,
        )


def get_weighted_quota_shots_between(
    person_id, start, end, project_id=None, task_type_id=None, feedback=True
):
    """
    Get all shots leading to a quota computation during the given period.
    Set a weight on each one:
        * If there is time spent filled, weight it by the sum of duration
          divided py the overall task duration.
        * If there is no time spent, weight it by the number of business days
          in the time interval spent between WIP date (start) and
          feedback date (end).
    """
    shot_type = get_shot_type()
    person = persons_service.get_person_raw(person_id)
    shots = []
    already_listed = {}

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(TimeSpent.person_id == person_id)
        .filter(TimeSpent.date >= func.cast(start, TimeSpent.date.type))
        .filter(TimeSpent.date < func.cast(end, TimeSpent.date.type))
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .join(TimeSpent, Task.id == TimeSpent.task_id)
        .add_columns(Task.duration, TimeSpent.duration)
    )

    if feedback:
        query = query.filter(Task.end_date != None)
    else:
        query = query.filter(Task.done_date != None)

    query_shots = query.all()
    for entity, task_duration, duration in query_shots:
        shot = entity.serialize()
        if shot["id"] not in already_listed:
            full_name, _, _ = names_service.get_full_entity_name(shot["id"])
            shot["full_name"] = full_name
            shot["weight"] = round(duration / task_duration, 2) or 0
            shots.append(shot)
            already_listed[shot["id"]] = shot
        else:
            shot = already_listed[shot["id"]]
            shot["weight"] += round(duration / task_duration, 2)

    if type(start) is str:
        start = date_helpers.get_datetime_from_string(start)
    if type(end) is str:
        end = date_helpers.get_datetime_from_string(end)
    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(Task.real_start_date != None)
        .filter(Task.assignees.contains(person))
        .filter(TimeSpent.id == None)
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
        .outerjoin(TimeSpent, TimeSpent.task_id == Task.id)
    )

    if feedback:
        query = (
            query.filter(Task.end_date != None)
            .filter((Task.real_start_date <= end) & (Task.end_date >= start))
            .add_columns(Task.real_start_date, Task.end_date)
        )
    else:
        query = (
            query.filter(Task.done_date != None)
            .filter((Task.real_start_date <= end) & (Task.done_date >= start))
            .add_columns(Task.real_start_date, Task.done_date)
        )

    query_shots = query.all()

    for entity, task_start, task_end in query_shots:
        shot = entity.serialize()
        if shot["id"] not in already_listed:
            business_days = (
                date_helpers.get_business_days(task_start, task_end) + 1
            )
            full_name, _, _ = names_service.get_full_entity_name(shot["id"])
            shot["full_name"] = full_name
            multiplicator = 1
            if task_start >= start and task_end <= end:
                multiplicator = business_days
            elif task_start >= start:
                multiplicator = (
                    date_helpers.get_business_days(task_start, end) + 1
                )
            elif task_end <= end:
                multiplicator = (
                    date_helpers.get_business_days(start, task_end) + 1
                )
            shot["weight"] = round(multiplicator / business_days, 2)
            already_listed[shot["id"]] = True
            shots.append(shot)

    return sorted(shots, key=itemgetter("full_name"))


def get_raw_quota_shots_between(
    person_id, start, end, project_id=None, task_type_id=None, feedback=True
):
    """
    Get all shots leading to a quota computation during the given period.
    """
    shot_type = get_shot_type()
    person = persons_service.get_person_raw(person_id)
    shots = []

    query = (
        Entity.query.filter(Entity.entity_type_id == shot_type["id"])
        .filter(Task.project_id == project_id)
        .filter(Task.task_type_id == task_type_id)
        .filter(Task.assignees.contains(person))
        .join(Task, Entity.id == Task.entity_id)
        .join(Project, Project.id == Task.project_id)
    )

    if feedback:
        query = query.filter(
            Task.end_date.between(
                func.cast(start, Task.end_date.type),
                func.cast(end, Task.end_date.type),
            )
        )
    else:
        query = query.filter(
            Task.done_date.between(
                func.cast(start, Task.done_date.type),
                func.cast(end, Task.done_date.type),
            )
        )

    query_shots = query.all()

    for entity in query_shots:
        shot = entity.serialize()
        full_name, _, _ = names_service.get_full_entity_name(shot["id"])
        shot["full_name"] = full_name
        shot["weight"] = 1
        shots.append(shot)

    return sorted(shots, key=itemgetter("full_name"))


def _get_timezoned_interval(start, end):
    """
    Get time intervals adapted to the user timezone.
    """
    timezone = user_service.get_timezone()
    return date_helpers.get_timezoned_interval(start, end, timezone)


def get_all_raw_shots():
    """
    Get all assets from the database.
    """
    query = Entity.query.filter(Entity.entity_type_id == get_shot_type()["id"])
    return query.all()


def set_frames_from_task_type_preview_files(
    project_id,
    task_type_id,
    episode_id=None,
):
    from zou.app import db

    shot_type = get_shot_type()
    Shot = aliased(Entity)
    Sequence = aliased(Entity)

    if episode_id is not None:
        subquery = (
            db.session.query(
                Shot.id.label("entity_id"),
                func.max(PreviewFile.created_at).label("max_created_at"),
            )
            .join(Task, PreviewFile.task_id == Task.id)
            .join(Shot, Task.entity_id == Shot.id)
            .join(Sequence, Sequence.id == Shot.parent_id)
            .filter(Shot.project_id == project_id)
            .filter(Shot.entity_type_id == shot_type["id"])
            .filter(Task.task_type_id == task_type_id)
            .filter(Sequence.parent_id == episode_id)
            .group_by(Shot.id)
            .subquery()
        )
    else:
        subquery = (
            db.session.query(
                Shot.id.label("entity_id"),
                func.max(PreviewFile.created_at).label("max_created_at"),
            )
            .join(Task, PreviewFile.task_id == Task.id)
            .join(Shot, Task.entity_id == Shot.id)
            .filter(Shot.project_id == project_id)
            .filter(Shot.entity_type_id == shot_type["id"])
            .filter(Task.task_type_id == task_type_id)
            .group_by(Shot.id)
            .subquery()
        )

    query = (
        db.session.query(Shot, PreviewFile.duration)
        .join(Task, Task.entity_id == Shot.id)
        .join(subquery, (Shot.id == subquery.c.entity_id))
        .join(
            PreviewFile,
            (PreviewFile.task_id == Task.id)
            & (PreviewFile.created_at == subquery.c.max_created_at),
        )
        .filter(Task.task_type_id == task_type_id)
        .filter(Shot.project_id == project_id)
    )

    results = query.all()
    project = projects_service.get_project(project_id)
    updates = []
    for shot, preview_duration in results:
        nb_frames = round(preview_duration * float(project["fps"]))
        updates.append(
            {
                "id": shot.id,
                "nb_frames": nb_frames,
            }
        )
        clear_shot_cache(str(shot.id))

    db.session.bulk_update_mappings(Shot, updates)
    db.session.commit()
    return updates
