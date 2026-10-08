from sqlalchemy.orm import aliased
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy import cast, func, Text

from zou.app.utils import (
    cache,
    events,
    fields,
    query as query_utils,
)

from zou.app.models.entity import (
    Entity,
    EntityVersion,
)
from zou.app.models.project import Project
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task

from zou.app.services import (
    base_service,
    entities_service,
    persons_service,
    projects_service,
    index_service,
    entity_types_service,
    subscriptions_service,
    metadata_descriptors_service,
)
from zou.app.exceptions import (
    EpisodeNotFoundException,
    SequenceNotFoundException,
    SceneNotFoundException,
    ShotNotFoundException,
    WrongIdFormatException,
)

# Field orders of the compact encoding of the with-tasks view. Clients
# must map values by reading these names from the response header, never
# by hardcoding positions.
SHOTS_AND_TASKS_SHOT_FIELDS = [
    "canceled",
    "data",
    "description",
    "entity_type_id",
    "episode_id",
    "episode_name",
    "fps",
    "frame_in",
    "frame_out",
    "id",
    "name",
    "nb_frames",
    "parent_id",
    "preview_file_id",
    "project_id",
    "project_name",
    "sequence_id",
    "sequence_name",
    "source_id",
    "nb_entities_out",
    "is_casting_standby",
    "type",
    "tasks",
]

SHOTS_AND_TASKS_TASK_FIELDS = [
    "id",
    "duration",
    "due_date",
    "end_date",
    "done_date",
    "entity_id",
    "estimation",
    "is_subscribed",
    "last_comment_date",
    "last_preview_file_id",
    "nb_assets_ready",
    "priority",
    "real_start_date",
    "retake_count",
    "start_date",
    "difficulty",
    "nb_drawings",
    "task_status_id",
    "task_type_id",
    "assignees",
    "data",
]


def clear_shot_cache(shot_id):
    """
    Drop every memoized serialization of given shot, the generic entity one
    included: a shot is a row of the entity table.
    """
    cache.cache.delete_memoized(get_shot, shot_id)
    cache.cache.delete_memoized(get_shot, shot_id, True)
    cache.cache.delete_memoized(get_full_shot, shot_id)
    entities_service.clear_entity_cache(shot_id)


def clear_sequence_cache(sequence_id):
    """
    Drop every memoized serialization of given sequence.
    """
    cache.cache.delete_memoized(get_sequence, sequence_id)
    cache.cache.delete_memoized(get_full_sequence, sequence_id)
    entities_service.clear_entity_cache(sequence_id)


def clear_episode_cache(episode_id):
    """
    Drop every memoized serialization of given episode.
    """
    cache.cache.delete_memoized(get_episode, episode_id)
    cache.cache.delete_memoized(get_episode_by_name)
    entities_service.clear_entity_cache(episode_id)


def get_episodes(criterions=None):
    """
    Get all episodes for given criterions.
    """
    if criterions is None:
        criterions = {}
    episode_type = entity_types_service.get_episode_type()
    criterions["entity_type_id"] = episode_type["id"]
    query = Entity.query.order_by(Entity.name)
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    try:
        episodes = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException
    return Entity.serialize_list(episodes, obj_type="Episode")


def get_sequences(criterions=None):
    """
    Get all sequences for given criterions.
    """
    if criterions is None:
        criterions = {}
    sequence_type = entity_types_service.get_sequence_type()
    criterions["entity_type_id"] = sequence_type["id"]
    query = Entity.query.order_by(Entity.name)
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    try:
        sequences = query.all()
    except StatementError:  # Occurs when an id is not properly formatted
        raise WrongIdFormatException
    return Entity.serialize_list(sequences, obj_type="Sequence")


def get_shots(criterions=None):
    """
    Get all shots for given criterions.
    """
    if criterions is None:
        criterions = {}
    shot_type = entity_types_service.get_shot_type()
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
    )

    if is_only_assignation:
        query = query.outerjoin(Task, Task.entity_id == Entity.id)
        query = query.filter(persons_service.build_assignee_filter())

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

    # Sort the dicts rather than the SQL rows: ordering thousands of
    # wide rows (data JSONB included) in PostgreSQL makes it materialize
    # the whole join before returning anything.
    shots.sort(key=lambda shot: shot["name"].casefold())

    return metadata_descriptors_service.remove_not_allowed_metadata_for_vendor(
        "Shot", criterions.get("vendor_departments"), shots
    )


def get_scenes(criterions=None):
    """
    Get all scenes for given criterions.
    """
    if criterions is None:
        criterions = {}
    scene_type = entity_types_service.get_scene_type()
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
        query = query.filter(persons_service.build_assignee_filter())

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


def prepare_shots_and_tasks(criterions=None, compact=False):
    """
    Run the with-tasks queries and return a generator yielding one shot
    at a time. With compact=True each item is a list of values aligned on
    SHOTS_AND_TASKS_SHOT_FIELDS (tasks aligned on
    SHOTS_AND_TASKS_TASK_FIELDS) instead of a dict.

    Three flat queries (shots, tasks, assignee links) instead of a single
    Entity x Task x TaskPersonLink join, and no per-row ORM
    materialization: the joined form dominated payload and memory on
    large productions (10k shots for series).

    All database and request-dependent work happens before this function
    returns: the generator is pure formatting, so a streaming response
    can consume it after the request context is gone, without the whole
    response ever being held in memory.
    """
    from zou.app import db

    if criterions is None:
        criterions = {}
    shot_type = entity_types_service.get_shot_type()
    subscription_map = subscriptions_service.get_subscriptions_for_user(
        criterions.get("project_id", None), shot_type["id"]
    )

    assigned_to = "assigned_to" in criterions
    if assigned_to:
        del criterions["assigned_to"]

    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")

    def apply_filters(query):
        query = query.filter(Entity.entity_type_id == shot_type["id"])
        if "id" in criterions:
            query = query.filter(Entity.id == criterions["id"])
        if "project_id" in criterions:
            query = query.filter(Entity.project_id == criterions["project_id"])
        if "episode_id" in criterions and criterions["episode_id"] != "all":
            query = query.filter(
                Sequence.parent_id == criterions["episode_id"]
            )
        if assigned_to:
            has_assigned_task = (
                db.session.query(Task.id)
                .filter(Task.entity_id == Entity.id)
                .filter(persons_service.build_assignee_filter())
                .exists()
            )
            query = query.filter(has_assigned_task)
        return query

    shot_rows = (
        apply_filters(
            Entity.query.join(Project, Project.id == Entity.project_id)
            .join(Sequence, Sequence.id == Entity.parent_id)
            .outerjoin(Episode, Episode.id == Sequence.parent_id)
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
            Entity.nb_frames,
            Entity.nb_entities_out,
            Entity.is_casting_standby,
            cast(Entity.project_id, Text).label("project_id"),
            cast(Episode.id, Text).label("episode_id"),
            Episode.name.label("episode_name"),
            cast(Sequence.id, Text).label("sequence_id"),
            Sequence.name.label("sequence_name"),
            Project.name.label("project_name"),
        )
        .all()
    )

    def apply_task_filters(query):
        return apply_filters(
            query.join(Sequence, Sequence.id == Entity.parent_id)
        )

    tasks_by_entity, build_task = entities_service.fetch_entity_task_map(
        apply_task_filters,
        subscription_map,
        SHOTS_AND_TASKS_TASK_FIELDS,
        assigned_to=assigned_to,
        compact=compact,
    )

    not_allowed_map = None
    if "vendor_departments" in criterions:
        not_allowed_map = metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
            "Shot",
            criterions["vendor_departments"],
            set(row.project_id for row in shot_rows),
        )

    def iterate():
        for row in shot_rows:
            data = fields.serialize_value(row.data or {})
            if not_allowed_map is not None:
                data = metadata_descriptors_service.remove_not_allowed_fields_from_metadata(
                    not_allowed_map[row.project_id], data
                )
            tasks = [
                build_task(task_row)
                for task_row in tasks_by_entity.get(row.id, ())
            ]
            if compact:
                yield [
                    row.canceled,
                    data,
                    row.description,
                    row.entity_type_id,
                    row.episode_id,
                    row.episode_name or "",
                    data.get("fps", None),
                    data.get("frame_in", None),
                    data.get("frame_out", None),
                    row.id,
                    row.name,
                    row.nb_frames,
                    row.parent_id,
                    row.preview_file_id,
                    row.project_id,
                    row.project_name,
                    row.sequence_id,
                    row.sequence_name,
                    row.source_id,
                    row.nb_entities_out,
                    row.is_casting_standby,
                    "Shot",
                    tasks,
                ]
            else:
                yield {
                    "canceled": row.canceled,
                    "data": data,
                    "description": row.description,
                    "entity_type_id": row.entity_type_id,
                    "episode_id": row.episode_id,
                    "episode_name": row.episode_name or "",
                    "fps": data.get("fps", None),
                    "frame_in": data.get("frame_in", None),
                    "frame_out": data.get("frame_out", None),
                    "id": row.id,
                    "name": row.name,
                    "nb_frames": row.nb_frames,
                    "parent_id": row.parent_id,
                    "preview_file_id": row.preview_file_id,
                    "project_id": row.project_id,
                    "project_name": row.project_name,
                    "sequence_id": row.sequence_id,
                    "sequence_name": row.sequence_name,
                    "source_id": row.source_id,
                    "nb_entities_out": row.nb_entities_out,
                    "is_casting_standby": row.is_casting_standby,
                    "tasks": tasks,
                    "type": "Shot",
                }

    return iterate()


def get_shots_and_tasks(criterions=None):
    """
    Get all shots for given criterions with related tasks for each shot,
    as a list of dicts.
    """
    return list(prepare_shots_and_tasks(criterions))


def _get_typed_entity_by_shotgun_id(entity_type, shotgun_id, exception):
    """
    Return the entity of given type matching given shotgun id as an active
    record.
    """
    entity = Entity.get_by(
        entity_type_id=entity_type["id"], shotgun_id=shotgun_id
    )
    if entity is None:
        raise exception
    return entity


def get_shot_raw(shot_id):
    """
    Return given shot as an active record.
    """
    return base_service.get_typed_instance(
        Entity,
        shot_id,
        entity_types_service.get_shot_type()["id"],
        ShotNotFoundException,
    )


@cache.memoize_function(120)
def get_shot(shot_id, relations=False):
    """
    Return given shot as a dictionary.
    """
    return get_shot_raw(shot_id).serialize(
        obj_type="Shot", relations=relations
    )


@cache.memoize_function_single_flight(120)
def get_full_shot(shot_id):
    """
    Return given shot as a dictionary with extra data like project and
    sequence names.
    """
    if not fields.is_valid_id(shot_id):
        raise ShotNotFoundException
    shots = get_shots_and_tasks({"id": shot_id})
    if len(shots) == 0:
        raise ShotNotFoundException
    shot = shots[0]
    shot.update(get_shot(shot_id, relations=True))
    return shot


def get_scene_raw(scene_id):
    """
    Return given scene as an active record.
    """
    return base_service.get_typed_instance(
        Entity,
        scene_id,
        entity_types_service.get_scene_type()["id"],
        SceneNotFoundException,
    )


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
    return base_service.get_typed_instance(
        Entity,
        sequence_id,
        entity_types_service.get_sequence_type()["id"],
        SequenceNotFoundException,
    )


@cache.memoize_function(120)
def get_sequence(sequence_id):
    """
    Return given sequence as a dictionary.
    """
    return get_sequence_raw(sequence_id).serialize(obj_type="Sequence")


@cache.memoize_function_single_flight(120)
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
    sequence = None
    if shot.get("parent_id") is not None:
        try:
            sequence = Entity.get(shot["parent_id"])
        except Exception:
            sequence = None
    # Entity.get(None) returns None without raising, so the absence has
    # to be checked, not caught.
    if sequence is None:
        raise SequenceNotFoundException("Wrong parent_id for given shot.")
    return sequence.serialize(obj_type="Sequence")


def get_episode_raw(episode_id):
    """
    Return given episode as an active record.
    """
    return base_service.get_typed_instance(
        Entity,
        episode_id,
        entity_types_service.get_episode_type()["id"],
        EpisodeNotFoundException,
    )


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
    episode_type_id = entity_types_service.get_episode_type()["id"]
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
    episode = None
    if sequence.get("parent_id") is not None:
        try:
            episode = Entity.get(sequence["parent_id"])
        except Exception:
            episode = None
    if episode is None:
        raise EpisodeNotFoundException("Wrong parent_id for given sequence.")
    return episode.serialize(obj_type="Episode")


def get_shot_by_shotgun_id(shotgun_id):
    """
    Retrieves a shot identifed by its shotgun ID (stored during import).
    """
    return _get_typed_entity_by_shotgun_id(
        entity_types_service.get_shot_type(), shotgun_id, ShotNotFoundException
    ).serialize(obj_type="Shot")


def get_scene_by_shotgun_id(shotgun_id):
    """
    Retrieves a scene identifed by its shotgun ID (stored during import).
    """
    return _get_typed_entity_by_shotgun_id(
        entity_types_service.get_scene_type(),
        shotgun_id,
        SceneNotFoundException,
    ).serialize(obj_type="Scene")


def get_sequence_by_shotgun_id(shotgun_id):
    """
    Retrieves a sequence identifed by its shotgun ID (stored during import).
    """
    return _get_typed_entity_by_shotgun_id(
        entity_types_service.get_sequence_type(),
        shotgun_id,
        SequenceNotFoundException,
    ).serialize(obj_type="Sequence")


def get_episode_by_shotgun_id(shotgun_id):
    """
    Retrieves an episode identifed by its shotgun ID (stored during import).
    """
    return _get_typed_entity_by_shotgun_id(
        entity_types_service.get_episode_type(),
        shotgun_id,
        EpisodeNotFoundException,
    ).serialize(obj_type="Episode")


def get_or_create_first_episode(project_id, created_by=None):
    """
    Get the first episode of the production.
    """
    episode_type = entity_types_service.get_episode_type()
    episode = (
        Entity.query.filter_by(
            project_id=project_id, entity_type_id=episode_type["id"]
        )
        .order_by(Entity.name)
        .first()
    )
    if episode is not None:
        return episode.serialize()
    else:
        return create_episode(project_id, "E01", created_by=created_by)


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
            .filter(persons_service.build_assignee_filter())
        )
        shot_episodes = fields.serialize_models(query.all())
        shot_episode_ids = {episode["id"]: True for episode in shot_episodes}
        query = (
            Entity.query.join(Asset, Entity.id == Asset.source_id)
            .join(Task, Asset.id == Task.entity_id)
            .filter(Entity.project_id == project_id)
            .filter(persons_service.build_assignee_filter())
        )
        asset_episodes = fields.serialize_models(query.all())
        result = shot_episodes
        for episode in asset_episodes:
            if episode["id"] not in shot_episode_ids:
                result.append(episode)
        return result
    else:
        return entities_service.get_entities_for_project(
            project_id,
            entity_types_service.get_episode_type()["id"],
            "Episode",
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
            .filter(persons_service.build_assignee_filter())
        )
        return fields.serialize_models(query.all())
    else:
        return entities_service.get_entities_for_project(
            project_id,
            entity_types_service.get_sequence_type()["id"],
            "Sequence",
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
            .filter(persons_service.build_assignee_filter())
        )
        return fields.serialize_models(query.all())
    else:
        return get_sequences({"parent_id": episode_id})


def get_shots_for_project(project_id, only_assigned=False):
    """
    Retrieve all shots related to given project.
    """
    return entities_service.get_entities_for_project(
        project_id,
        entity_types_service.get_shot_type()["id"],
        "Shot",
        only_assigned=only_assigned,
    )


def get_shots_for_episode(episode_id, relations=False):
    """
    Get all shots for given episode.
    """
    Sequence = aliased(Entity, name="sequence")
    shot_type_id = entity_types_service.get_shot_type()["id"]
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
        entity_types_service.get_scene_type()["id"],
        "Scene",
        only_assigned=only_assigned,
    )


def get_scenes_for_sequence(sequence_id):
    """
    Retrieve all scenes children of given sequence.
    """
    get_sequence(sequence_id)
    scene_type_id = entity_types_service.get_scene_type()["id"]
    result = (
        Entity.query.filter(Entity.entity_type_id == scene_type_id)
        .filter(Entity.parent_id == sequence_id)
        .order_by(Entity.name)
        .all()
    )
    return Entity.serialize_list(result, "Scene")


def create_episode(
    project_id,
    name,
    status="running",
    description="",
    data=None,
    created_by=None,
):
    """
    Create episode for given project.
    """
    if data is None:
        data = {}
    episode_type = entity_types_service.get_episode_type()
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
    project_id, episode_id, name, description="", data=None, created_by=None
):
    """
    Create sequence for given project and episode.
    """
    if data is None:
        data = {}
    sequence_type = entity_types_service.get_sequence_type()

    if episode_id is not None:
        episode = get_episode(episode_id)  # raises if it fails.
        if episode["project_id"] != str(project_id):
            raise EpisodeNotFoundException

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
    data=None,
    nb_frames=0,
    description=None,
    created_by=None,
    index=True,
):
    """
    Create shot for given project and sequence. A bulk import passes
    index=False and indexes all its shots at the end.
    """
    if data is None:
        data = {}
    shot_type = entity_types_service.get_shot_type()

    sequence = None
    if sequence_id is not None:
        # raises SequenceNotFound if it fails.
        sequence = get_sequence(sequence_id)
        if sequence["project_id"] != str(project_id):
            raise SequenceNotFoundException

    lookup = {
        "entity_type_id": shot_type["id"],
        "parent_id": sequence_id,
        "project_id": project_id,
        "name": name,
    }
    shot = Entity.get_by(**lookup)
    if shot is None:
        try:
            shot = Entity.create(
                data=data,
                nb_frames=nb_frames,
                description=description,
                created_by=created_by,
                **lookup,
            )
        except IntegrityError:
            shot = Entity.get_by(**lookup)
            if shot is None:
                raise
        else:
            if index:
                index_service.index_shot(shot)
            events.emit(
                "shot:new",
                {
                    "shot_id": shot.id,
                    # A production that has not laid out its sequences yet
                    # creates shots with no parent at all, and the route
                    # allows it.
                    "episode_id": (
                        sequence["parent_id"] if sequence is not None else None
                    ),
                },
                project_id=project_id,
            )

    return shot.serialize(obj_type="Shot")


def create_scene(project_id, sequence_id, name, created_by=None):
    """
    Create scene for given project and sequence.
    """
    scene_type = entity_types_service.get_scene_type()

    if sequence_id is not None:
        # raises SequenceNotFound if it fails.
        sequence = get_sequence(sequence_id)
        if sequence["project_id"] != str(project_id):
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


def update_shot(shot_id, data_dict, index=True):
    """
    Update shot fields matching given id with data from dict given in parameter.
    A bulk import passes index=False and indexes all its shots at the end.
    """
    shot = get_shot_raw(shot_id)
    shot.update(data_dict)

    if index:
        index_service.remove_shot_index(shot.id)
        index_service.index_shot(shot)
    clear_shot_cache(shot_id)
    events.emit(
        "shot:update", {"shot_id": shot_id}, project_id=str(shot.project_id)
    )

    return shot.serialize()


def get_shot_versions(shot_id):
    """
    Return all versions of given shot, most recent first. A version is
    recorded when the frame range or the name of the shot changes.
    """
    versions = (
        EntityVersion.query.filter_by(entity_id=shot_id)
        .order_by(EntityVersion.created_at.desc())
        .all()
    )
    return EntityVersion.serialize_list(versions, obj_type="ShotVersion")


def get_last_shot_version_raw(shot_id):
    """
    Return the most recent version of given shot as a model, or None when
    the shot was never versioned.
    """
    return (
        EntityVersion.query.filter_by(entity_id=shot_id)
        .order_by(EntityVersion.created_at.desc())
        .first()
    )


def get_all_raw_shots():
    """
    Get all shots from the database.
    """
    query = Entity.query.filter(
        Entity.entity_type_id == entity_types_service.get_shot_type()["id"]
    )
    return query.all()


def set_frames_from_task_type_preview_files(
    project_id,
    task_type_id,
    episode_id=None,
):
    """
    Set the frame count of each shot from the duration of the last preview
    of given task type. Used to backfill nb_frames from the movies actually
    delivered.
    """
    from zou.app import db

    shot_type = entity_types_service.get_shot_type()
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
