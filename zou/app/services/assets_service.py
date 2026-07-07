from sqlalchemy import cast, or_, Text
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import aliased

from zou.app import db
from zou.app.utils import events, fields, cache
from zou.app.utils import query as query_utils

from zou.app.models.entity import (
    Entity,
    EntityLink,
    EntityConceptLink,
    EntityVersion,
)
from zou.app.models.entity_type import EntityType
from zou.app.models.subscription import Subscription
from zou.app.models.project import Project
from zou.app.models.task import Task, TaskPersonLink
from zou.app.models.asset_instance import AssetInstance

from zou.app.services import (
    base_service,
    breakdown_service,
    deletion_service,
    edits_service,
    index_service,
    notifications_service,
    projects_service,
    shots_service,
    user_service,
    entities_service,
    concepts_service,
)

from zou.app.services.exception import (
    AssetNotFoundException,
    AssetInstanceNotFoundException,
    AssetTypeNotFoundException,
)


def clear_asset_cache(asset_id):
    cache.cache.delete_memoized(get_asset, asset_id)
    cache.cache.delete_memoized(get_asset, asset_id, True)
    cache.cache.delete_memoized(get_full_asset, asset_id)


def clear_asset_type_cache():
    cache.cache.delete_memoized(get_all_asset_types)


def get_temporal_type_ids():
    shot_type = shots_service.get_shot_type()
    scene_type = shots_service.get_scene_type()
    sequence_type = shots_service.get_sequence_type()
    episode_type = shots_service.get_episode_type()
    edit_type = edits_service.get_edit_type()
    concept_type = concepts_service.get_concept_type()

    return [
        shot_type["id"],
        sequence_type["id"],
        episode_type["id"],
        edit_type["id"],
        scene_type["id"],
        concept_type["id"],
    ]


def build_asset_type_filter():
    """
    Generate a query filter to filter entity that are assets (it means not shot,
    not sequence, not episode and not scene)
    """
    ids_to_exclude = get_temporal_type_ids()
    return ~Entity.entity_type_id.in_(ids_to_exclude)


def build_entity_type_asset_type_filter():
    """
    Generate a query filter to filter entity types that are asset types (it
    means not shot, not sequence, not episode and not scene)
    """
    ids_to_exclude = get_temporal_type_ids()
    return ~EntityType.id.in_(ids_to_exclude)


def get_assets(criterions=None, is_admin=False):
    """
    Get all assets for given criterions.
    """
    if criterions is None:
        criterions = {}
    query = Entity.query.filter(build_asset_type_filter())
    assigned_to = False
    episode_id = None
    if "assigned_to" in criterions:
        assigned_to = True
        del criterions["assigned_to"]
    if "episode_id" in criterions:
        episode_id = criterions["episode_id"]
        del criterions["episode_id"]
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    if assigned_to:
        query = query.outerjoin(Task)
        query = query.filter(user_service.build_assignee_filter())

    if "is_shared" in criterions:
        if not is_admin:
            query = query.join(Project).filter(
                user_service.build_team_filter()
            )

    if episode_id is not None:
        # Filter based on main episode.
        query = query.filter(Entity.source_id == episode_id)
        result = query.all()
        # Filter based on episode casting.
        query = (
            Entity.query.join(
                EntityLink, EntityLink.entity_out_id == Entity.id
            )
            .filter(EntityLink.entity_in_id == episode_id)
            .filter(build_asset_type_filter())
        )
        query = query_utils.apply_criterions_to_db_query(
            Entity, query, criterions
        )
        # Add non duplicated assets to the list.
        result += [a for a in query.all() if a.source_id != episode_id]
    else:
        result = query.all()
    return Entity.serialize_list(result, obj_type="Asset")


def get_all_raw_assets():
    """
    Get all assets from the database.
    """
    query = Entity.query.filter(build_asset_type_filter())
    return query.all()


def get_full_assets(criterions=None):
    """
    Get all assets for given criterions with additional informations: project
    name and asset type name.
    """
    if criterions is None:
        criterions = {}
    assigned_to = False
    if "assigned_to" in criterions:
        assigned_to = True
        del criterions["assigned_to"]

    query = (
        Entity.query.filter_by(**criterions)
        .filter(build_asset_type_filter())
        .join(Project)
        .join(EntityType)
        .add_columns(Project.name, EntityType.name)
        .order_by(Project.name, EntityType.name, Entity.name)
    )
    if assigned_to:
        query = query.outerjoin(Task)
        query = query.filter(user_service.build_assignee_filter())
    data = query.all()
    assets = []
    for asset_model, project_name, asset_type_name in data:
        asset = asset_model.serialize(obj_type="Asset")
        asset["project_name"] = project_name
        asset["asset_type_name"] = asset_type_name
        assets.append(asset)
    return assets


def _serialize_datetime(value):
    """
    Specialized serializer for the with-tasks hot loop: the task date
    columns are all DateTime, so the type-dispatch of
    fields.serialize_value (6 calls per task) is pure overhead there.
    """
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat()


def _apply_asset_and_tasks_criterions(query, criterions, assigned_to):
    """
    Apply the with-tasks asset filters (asset types only, id, project,
    episode casting, assigned to current user) on a query that has Entity
    in its FROM clause. Episode casting and assignation are expressed as
    EXISTS subqueries so no filter ever multiplies the result rows.
    """
    query = query.filter(build_asset_type_filter())

    if "id" in criterions:
        query = query.filter(Entity.id == criterions["id"])

    if "project_id" in criterions:
        query = query.filter(Entity.project_id == criterions["project_id"])

    if "episode_id" in criterions:
        episode_id = criterions["episode_id"]
        if episode_id == "main":
            query = query.filter(Entity.source_id == None)
        elif episode_id != "all":
            cast_in_episode = (
                db.session.query(EntityLink.entity_out_id)
                .filter(EntityLink.entity_out_id == Entity.id)
                .filter(EntityLink.entity_in_id == episode_id)
                .exists()
            )
            query = query.filter(
                or_(Entity.source_id == episode_id, cast_in_episode)
            )

    if assigned_to:
        has_assigned_task = (
            db.session.query(Task.id)
            .filter(Task.entity_id == Entity.id)
            .filter(user_service.build_assignee_filter())
            .exists()
        )
        query = query.filter(has_assigned_task)

    return query


# Field orders of the compact encoding of the with-tasks views. Clients
# must map values by reading these names from the response header, never
# by hardcoding positions.
ASSETS_AND_TASKS_ASSET_FIELDS = [
    "id",
    "name",
    "preview_file_id",
    "description",
    "asset_type_name",
    "asset_type_id",
    "canceled",
    "ready_for",
    "episode_id",
    "casting_episode_ids",
    "is_casting_standby",
    "is_shared",
    "data",
    "tasks",
]
ASSETS_AND_TASKS_TASK_FIELDS = [
    "id",
    "due_date",
    "done_date",
    "duration",
    "entity_id",
    "estimation",
    "end_date",
    "is_subscribed",
    "last_comment_date",
    "last_preview_file_id",
    "priority",
    "real_start_date",
    "retake_count",
    "start_date",
    "difficulty",
    "task_status_id",
    "task_type_id",
    "assignees",
]


def prepare_assets_and_tasks(
    criterions=None, with_episode_ids=False, compact=False
):
    """
    Run the with-tasks queries and return a generator yielding one asset
    at a time, in display order. With compact=True each item is a list of
    values aligned on ASSETS_AND_TASKS_ASSET_FIELDS (tasks aligned on
    ASSETS_AND_TASKS_TASK_FIELDS) instead of a dict, which halves the
    payload of task-heavy views.

    Three flat queries (assets, tasks, assignee links) instead of a
    single Entity x Task x TaskPersonLink join: the joined form returned
    one row per (asset, task, assignee) with every asset column repeated
    on each row, which dominated the payload, the sort and the Python
    dedup on large productions.

    All database and request-dependent work happens before this function
    returns: the generator is pure formatting, so a streaming response
    can consume it after the request context is gone, without the whole
    response ever being held in memory.
    """
    if criterions is None:
        criterions = {}
    Episode = aliased(Entity, name="episode")
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), None
    )

    assigned_to = "assigned_to" in criterions
    if assigned_to:
        del criterions["assigned_to"]

    asset_rows = (
        _apply_asset_and_tasks_criterions(
            Entity.query.join(
                EntityType, Entity.entity_type_id == EntityType.id
            ),
            criterions,
            assigned_to,
        )
        .with_entities(
            Entity.id,
            Entity.name,
            Entity.description,
            Entity.data,
            Entity.preview_file_id,
            Entity.entity_type_id,
            Entity.canceled,
            Entity.ready_for,
            Entity.source_id,
            Entity.is_casting_standby,
            Entity.is_shared,
            Entity.project_id,
            EntityType.name.label("asset_type_name"),
        )
        .order_by(EntityType.name, Entity.name)
        .all()
    )

    task_query = _apply_asset_and_tasks_criterions(
        Task.query.join(Entity, Task.entity_id == Entity.id),
        criterions,
        assigned_to,
    ).with_entities(
        # uuid::text in SQL: casting 4-5 uuids per task row in Python
        # (uuid.__str__ + the UUID result processor) shows up in profiles
        # at 75k tasks.
        cast(Task.id, Text).label("id"),
        cast(Task.entity_id, Text).label("entity_id"),
        cast(Task.task_type_id, Text).label("task_type_id"),
        cast(Task.task_status_id, Text).label("task_status_id"),
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
        cast(Task.last_preview_file_id, Text).label("last_preview_file_id"),
        Task.difficulty,
    )
    if assigned_to:
        task_query = task_query.filter(user_service.build_assignee_filter())
    task_rows = task_query.all()

    link_query = _apply_asset_and_tasks_criterions(
        db.session.query(TaskPersonLink)
        .join(Task, TaskPersonLink.task_id == Task.id)
        .join(Entity, Task.entity_id == Entity.id),
        criterions,
        assigned_to,
    ).with_entities(
        cast(TaskPersonLink.task_id, Text),
        cast(TaskPersonLink.person_id, Text),
    )
    if assigned_to:
        link_query = link_query.filter(user_service.build_assignee_filter())
    link_rows = link_query.all()

    cast_in_episode_ids = {}
    if "project_id" in criterions or with_episode_ids:
        episode_links_query = (
            EntityLink.query.join(
                Episode, EntityLink.entity_in_id == Episode.id
            )
            .join(EntityType, EntityType.id == Episode.entity_type_id)
            .filter(EntityType.name == "Episode")
            .order_by(Episode.name)
        )

        if "project_id" in criterions:
            episode_links_query = episode_links_query.filter(
                Episode.project_id == criterions["project_id"]
            )
        if "episode_id" in criterions and criterions["episode_id"] not in [
            "main",
            "all",
        ]:
            episode_links_query = episode_links_query.filter(
                EntityLink.entity_in_id == criterions["episode_id"]
            )
        if "id" in criterions:
            episode_links_query = episode_links_query.filter(
                EntityLink.entity_out_id == criterions["id"]
            )

        for link in episode_links_query.all():
            if str(link.entity_out_id) not in cast_in_episode_ids:
                cast_in_episode_ids[str(link.entity_out_id)] = []
            cast_in_episode_ids[str(link.entity_out_id)].append(
                str(link.entity_in_id)
            )

    not_allowed_map = None
    if "vendor_departments" in criterions:
        not_allowed_map = (
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                "Asset",
                criterions["vendor_departments"],
                set(row.project_id for row in asset_rows),
            )
        )

    assignees_by_task = {}
    for task_id, person_id in link_rows:
        if person_id:
            assignees_by_task.setdefault(task_id, []).append(person_id)

    tasks_by_entity = {}
    for row in task_rows:
        tasks_by_entity.setdefault(row.entity_id, []).append(row)

    if compact:

        def build_task(row):
            return [
                row.id,
                _serialize_datetime(row.due_date),
                _serialize_datetime(row.done_date),
                row.duration,
                row.entity_id,
                row.estimation,
                _serialize_datetime(row.end_date),
                subscription_map.get(row.id, False),
                _serialize_datetime(row.last_comment_date),
                row.last_preview_file_id or "",
                row.priority or 0,
                _serialize_datetime(row.real_start_date),
                row.retake_count,
                _serialize_datetime(row.start_date),
                row.difficulty,
                row.task_status_id,
                row.task_type_id,
                assignees_by_task.get(row.id, []),
            ]

    else:

        def build_task(row):
            return {
                "id": row.id,
                "due_date": _serialize_datetime(row.due_date),
                "done_date": _serialize_datetime(row.done_date),
                "duration": row.duration,
                "entity_id": row.entity_id,
                "estimation": row.estimation,
                "end_date": _serialize_datetime(row.end_date),
                "is_subscribed": subscription_map.get(row.id, False),
                "last_comment_date": _serialize_datetime(
                    row.last_comment_date
                ),
                "last_preview_file_id": row.last_preview_file_id or "",
                "priority": row.priority or 0,
                "real_start_date": _serialize_datetime(row.real_start_date),
                "retake_count": row.retake_count,
                "start_date": _serialize_datetime(row.start_date),
                "difficulty": row.difficulty,
                "task_status_id": row.task_status_id,
                "task_type_id": row.task_type_id,
                "assignees": assignees_by_task.get(row.id, []),
            }

    def iterate():
        for row in asset_rows:
            asset_id = str(row.id)
            data = fields.serialize_value(row.data or {})
            if not_allowed_map is not None:
                data = (
                    entities_service.remove_not_allowed_fields_from_metadata(
                        not_allowed_map[row.project_id], data
                    )
                )
            tasks = [
                build_task(task_row)
                for task_row in tasks_by_entity.get(asset_id, ())
            ]
            if compact:
                yield [
                    asset_id,
                    row.name,
                    str(row.preview_file_id or ""),
                    row.description,
                    row.asset_type_name,
                    str(row.entity_type_id),
                    row.canceled,
                    str(row.ready_for),
                    str(row.source_id) if row.source_id else "",
                    cast_in_episode_ids.get(asset_id, []),
                    row.is_casting_standby,
                    row.is_shared,
                    data,
                    tasks,
                ]
            else:
                yield {
                    "id": asset_id,
                    "name": row.name,
                    "preview_file_id": str(row.preview_file_id or ""),
                    "description": row.description,
                    "asset_type_name": row.asset_type_name,
                    "asset_type_id": str(row.entity_type_id),
                    "canceled": row.canceled,
                    "ready_for": str(row.ready_for),
                    "episode_id": str(row.source_id) if row.source_id else "",
                    "casting_episode_ids": cast_in_episode_ids.get(
                        asset_id, []
                    ),
                    "is_casting_standby": row.is_casting_standby,
                    "is_shared": row.is_shared,
                    "data": data,
                    "tasks": tasks,
                }

    return iterate()


def get_assets_and_tasks(criterions=None, with_episode_ids=False):
    """
    Get all assets for given criterions with related tasks for each
    asset, as a list of dicts.
    """
    return list(prepare_assets_and_tasks(criterions, with_episode_ids))


def get_asset_types(criterions=None):
    """
    Retrieve all asset types available. Only the no-criterion variant is
    memoized: criterion dicts vary per request and used to pollute the
    cache with entries that were never hit again.
    """
    if not criterions:
        return get_all_asset_types()
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    return EntityType.serialize_list(
        query.all(), obj_type="AssetType", relations=True
    )


@cache.memoize_function(240)
def get_all_asset_types():
    """
    Retrieve all asset types, without criterion.
    """
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    return EntityType.serialize_list(
        query.all(), obj_type="AssetType", relations=True
    )


def get_asset_types_for_project(project_id):
    """
    Retrieve all asset types related to asset of a given project.
    """
    asset_type_ids = {
        x["entity_type_id"] for x in get_assets({"project_id": project_id})
    }

    if len(asset_type_ids) > 0:
        result = EntityType.query.filter(
            EntityType.id.in_(list(asset_type_ids))
        ).all()
    else:
        result = []
    return EntityType.serialize_list(result, obj_type="AssetType")


def get_asset_types_for_shot(shot_id):
    """
    Retrieve all asset types related to asset casted in a given shot.
    """
    shot = Entity.get(shot_id)
    asset_type_ids = {x.entity_type_id for x in shot.entities_out}

    if len(asset_type_ids) > 0:
        query = EntityType.query
        query = query.filter(EntityType.id.in_(list(asset_type_ids)))
        result = query.all()
    else:
        result = []
    return EntityType.serialize_list(result, obj_type="AssetType")


def get_asset_raw(entity_id):
    """
    Return a given asset as an active record.
    """
    try:
        entity = Entity.get(entity_id)
    except StatementError:
        raise AssetNotFoundException

    if entity is None or not is_asset(entity):
        raise AssetNotFoundException

    return entity


@cache.memoize_function(120)
def get_asset(entity_id, relations=False):
    """
    Return a given asset as a dict.
    """
    return get_asset_raw(entity_id).serialize(
        obj_type="Asset", relations=relations
    )


def get_asset_by_shotgun_id(shotgun_id):
    """
    Return asset matching given shotgun ID as a dict.
    """
    assets = get_assets({"shotgun_id": shotgun_id})
    if len(assets) > 0:
        return assets[0]
    else:
        raise AssetNotFoundException


def get_raw_asset_by_shotgun_id(shotgun_id):
    """
    Return asset matching given shotgun ID as an active record.
    """
    asset = get_asset_by_shotgun_id(shotgun_id)
    return get_asset_raw(asset["id"])


@cache.memoize_function_single_flight(120)
def get_full_asset(asset_id):
    """
    Return asset matching given id with additional information (project name,
    asset type name and tasks).
    """
    assets = get_assets_and_tasks({"id": asset_id}, with_episode_ids=True)
    if len(assets) > 0:
        asset = dict(get_asset(asset_id, relations=True))
        asset_type_id = asset["entity_type_id"]
        asset_type = get_asset_type(asset_type_id)
        project = Project.get(asset["project_id"])

        asset["project_name"] = project.name
        asset["asset_type_id"] = asset_type["id"]
        asset["asset_type_name"] = asset_type["name"]
        del asset["source_id"]
        del asset["nb_frames"]
        asset.update(assets[0])
        return asset
    else:
        raise AssetNotFoundException


def get_asset_instance_raw(asset_instance_id):
    """
    Return given asset instance as active record.
    """
    return base_service.get_instance(
        AssetInstance, asset_instance_id, AssetInstanceNotFoundException
    )


def get_asset_instance(asset_instance_id):
    """
    Return given asset instance as a dict.
    """
    return get_asset_instance_raw(asset_instance_id).serialize()


def get_asset_type_raw(asset_type_id):
    """
    Return given asset type instance as active record.
    """
    try:
        asset_type = EntityType.get(asset_type_id)
    except StatementError:
        raise AssetTypeNotFoundException

    if asset_type is None or not is_asset_type(asset_type):
        raise AssetTypeNotFoundException

    return asset_type


@cache.memoize_function(240)
def get_asset_type(asset_type_id):
    """
    Return given asset type instance as a dict.
    """
    return get_asset_type_raw(asset_type_id).serialize(
        obj_type="AssetType", relations=True
    )


def get_or_create_asset_type(name):
    """
    For a given name, get matching asset type. Create if it does not exist.
    """
    asset_type = EntityType.get_by(name=name)
    if asset_type is None:
        asset_type = EntityType.create(name=name)
        clear_asset_type_cache()
        events.emit("asset-type:new", {"asset_type_id": asset_type.id})

    return asset_type.serialize(obj_type="AssetType")


def get_asset_type_by_name(asset_type_name):
    """
    Return asset type matching given name.
    """
    asset_type = EntityType.get_by(name=asset_type_name)
    if asset_type is None or not is_asset_type(asset_type):
        raise AssetTypeNotFoundException
    return asset_type.serialize(obj_type="AssetType")


def is_asset(entity):
    """
    Returns true if given entity is an asset, not a shot.
    """
    return str(entity.entity_type_id) not in get_temporal_type_ids()


def is_asset_dict(entity):
    """
    Returns true if given entity is an asset, not a shot.
    It supposes that the entity is represented as a dict.
    """
    return entity["entity_type_id"] not in get_temporal_type_ids()


def is_asset_type(entity_type):
    """
    Returns true if given entity type is an asset, not a shot.
    """
    entity_type_id = ""
    if isinstance(entity_type, dict):
        entity_type_id = entity_type.get("id", "")
    else:
        entity_type_id = str(entity_type.id)
    return entity_type_id not in get_temporal_type_ids()


def create_asset_types(asset_type_names):
    """
    For each name, create a new asset type.
    """
    asset_types = []
    for asset_type_name in asset_type_names:
        asset_type = get_or_create_asset_type(asset_type_name)
        asset_types.append(asset_type)

    return asset_types


def create_asset(
    project_id,
    asset_type_id,
    name,
    description,
    data,
    is_shared=False,
    source_id=None,
    created_by=None,
):
    """
    Create a new asset from given parameters.
    """
    project = projects_service.get_project_raw(project_id)
    asset_type = get_asset_type_raw(asset_type_id)
    if source_id is not None and len(source_id) < 36:
        source_id = None
    asset = Entity.create(
        project_id=project_id,
        entity_type_id=asset_type_id,
        name=name,
        description=description,
        data=data,
        is_shared=is_shared,
        source_id=source_id,
        created_by=created_by,
    )

    index_service.index_asset(asset)
    events.emit(
        "asset:new",
        {"asset_id": asset.id, "asset_type": asset_type.id},
        project_id=str(project.id),
    )

    return asset.serialize(obj_type="Asset")


def update_asset(asset_id, data):
    asset = get_asset_raw(asset_id)
    asset.update(data)

    index_service.remove_asset_index(asset_id)
    index_service.index_asset(asset)
    events.emit(
        "asset:update",
        {"asset_id": asset_id, "data": data},
        project_id=str(asset.project_id),
    )
    clear_asset_cache(asset_id)

    return asset.serialize(obj_type="Asset")


def remove_asset(asset_id, force=False):
    asset = get_asset_raw(asset_id)
    is_tasks_related = Task.query.filter_by(entity_id=asset_id).count() > 0

    if is_tasks_related and not force:
        asset.update({"canceled": True})
        clear_asset_cache(str(asset_id))
        events.emit(
            "asset:update",
            {"asset_id": asset_id},
            project_id=str(asset.project_id),
        )
        breakdown_service.refresh_casting_stats(
            asset.serialize(obj_type="Asset")
        )
    else:
        from zou.app.services import tasks_service

        # Before deleting EntityLinks, collect affected shot IDs so we can
        # refresh their casting stats after deletion
        cast_in = breakdown_service.get_cast_in(asset_id)
        affected_shot_ids = {
            entity["shot_id"] for entity in cast_in if "shot_id" in entity
        }

        tasks = Task.query.filter_by(entity_id=asset_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))
        index_service.remove_asset_index(str(asset_id))
        events.emit(
            "asset:delete",
            {"asset_id": asset_id},
            project_id=str(asset.project_id),
        )
        EntityVersion.delete_all_by(entity_id=asset_id)
        Subscription.delete_all_by(entity_id=asset_id)
        EntityLink.delete_all_by(entity_in_id=asset_id)
        EntityLink.delete_all_by(entity_out_id=asset_id)
        EntityConceptLink.delete_all_by(entity_in_id=asset_id)
        EntityConceptLink.delete_all_by(entity_out_id=asset_id)
        deletion_service.remove_output_files_for_entity(asset_id)
        for child in Entity.get_all_by(parent_id=asset_id):
            child.update({"parent_id": None})
        asset.delete()
        clear_asset_cache(str(asset_id))

        if affected_shot_ids:
            for shot_id in affected_shot_ids:
                shot = shots_service.get_shot(shot_id)
                breakdown_service.refresh_shot_casting_stats(shot)
    deleted_asset = asset.serialize(obj_type="Asset")
    return deleted_asset


def add_asset_link(asset_in_id, asset_out_id):
    """
    Link asset together, mark asset_in as asset out dependency.
    """
    asset_in = get_asset_raw(asset_in_id)
    asset_out = get_asset_raw(asset_out_id)

    if asset_out not in asset_in.entities_out:
        asset_in.entities_out.append(asset_out)
        asset_in.save()
        events.emit(
            "asset:new-link",
            {"asset_in": asset_in.id, "asset_out": asset_out.id},
            project_id=str(asset_in.project_id),
        )
    return asset_in.serialize(obj_type="Asset")


def remove_asset_link(asset_in_id, asset_out_id):
    """
    Remove link asset together, unmark asset_in as asset out dependency.
    """
    asset_in = get_asset_raw(asset_in_id)
    asset_out = get_asset_raw(asset_out_id)

    if asset_out in asset_in.entities_out:
        asset_in.entities_out = [
            x for x in asset_in.entities_out if x.id != asset_out_id
        ]
        asset_in.save()
        events.emit(
            "asset:remove-link",
            {"asset_in": asset_in.id, "asset_out": asset_out.id},
            project_id=str(asset_in.project_id),
        )
    return asset_in.serialize(obj_type="Asset")


def cancel_asset(asset_id, force=True):
    """
    Set cancel flag on asset to true. Send an event to event queue.
    """
    asset = get_asset_raw(asset_id)

    asset.update({"canceled": True})
    asset_dict = asset.serialize(obj_type="Asset")
    events.emit(
        "asset:delete",
        {"asset_id": asset_id},
        project_id=str(asset.project_id),
    )
    return asset_dict


def set_shared_assets(
    is_shared=True,
    project_id=None,
    asset_type_id=None,
    asset_ids=None,
    with_events=False,
):
    """
    Set all assets of a project to is_shared=True or False.
    """

    query = Entity.query.filter(build_asset_type_filter())

    if project_id is not None:
        query = query.filter(Entity.project_id == project_id)

    if asset_type_id is not None:
        query = query.filter(Entity.entity_type_id == asset_type_id)

    if asset_ids is not None:
        query = query.filter(Entity.id.in_(asset_ids))

    assets = query.all()

    for asset in assets:
        asset.update_no_commit({"is_shared": is_shared})

    Entity.commit()

    for asset in assets:
        asset_id = str(asset.id)
        clear_asset_cache(asset_id)
        if with_events:
            events.emit(
                "asset:update",
                {"asset_id": asset_id},
                project_id=project_id,
            )

    return Entity.serialize_list(assets, obj_type="Asset")


def get_shared_assets_used_in_project(project_id, episode_id=None):
    """
    Get all shared assets used in a project.
    """
    Shot = aliased(Entity, name="shot")
    Sequence = aliased(Entity, name="sequence")

    assets = (
        Entity.query.filter(build_asset_type_filter())
        .filter(Entity.is_shared == True)
        .join(EntityLink, EntityLink.entity_out_id == Entity.id)
        .join(Shot, EntityLink.entity_in_id == Shot.id)
        .join(Sequence, Shot.parent_id == Sequence.id)
        .filter(Shot.project_id == project_id)
        .filter(Entity.canceled != True)
        .filter(Entity.project_id != project_id)
    )

    if episode_id is not None and episode_id not in ["main", "all"]:
        assets = assets.filter(Sequence.parent_id == episode_id)

    return Entity.serialize_list(assets.all(), obj_type="Asset")
