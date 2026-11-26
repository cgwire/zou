from sqlalchemy import or_
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import aliased

from zou.app import db
from zou.app.exceptions import (
    AssetNotFoundException,
)
from zou.app.models.entity import (
    Entity,
    EntityLink,
)
from zou.app.models.entity_type import EntityType
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    entities_service,
    entity_types_service,
    index_service,
    metadata_descriptors_service,
    persons_service,
    projects_service,
    subscriptions_service,
)
from zou.app.utils import cache, events, fields, query as query_utils

# Field orders of the compact encoding of the with-tasks views. Clients
# must read these names from the response header to map the values.
# They must never use hardcoded positions.
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
    "data",
]


def clear_asset_cache(asset_id):
    """
    Drop all the memoized serializations of the given asset.

    An asset is a row of the entity table. Because of this, the generic
    entity serialization also goes: the entity names and the breakdown read
    the asset through it.
    """
    cache.cache.delete_memoized(get_asset, asset_id)
    cache.cache.delete_memoized(get_asset, asset_id, True)
    cache.cache.delete_memoized(get_full_asset, asset_id)
    entities_service.clear_entity_cache(asset_id)


def get_assets(
    criterions=None,
    only_user_projects=False,
    page=0,
    limit=None,
    cursor_id=None,
):
    """
    Return the assets that match the given criterions. The result is one of
    these:

    - all the assets.
    - a page of assets.
    - the assets after a cursor (see query_utils.get_paginated_results).

    Set only_user_projects on the routes that get their criterions from a
    client. Criterions without a project do not restrict the result.
    """
    if criterions is None:
        criterions = {}
    query = Entity.query.filter(entity_types_service.build_asset_type_filter())
    assigned_to = False
    episode_id = None
    if "assigned_to" in criterions:
        assigned_to = True
        del criterions["assigned_to"]
    if "episode_id" in criterions:
        episode_id = criterions["episode_id"]
        del criterions["episode_id"]
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
    if episode_id is not None:
        # The assets of the episode, and the assets cast in it.
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
        query = query.filter(entities_service.build_assigned_task_filter())
    if only_user_projects:
        query = query.filter(
            persons_service.build_team_exists_filter(Entity.project_id)
        )
    if not query_utils.is_whole_list(page, limit, cursor_id):
        query = query.order_by(Entity.name)
    result = query_utils.get_paginated_results(
        query,
        page,
        limit,
        cursor_id=cursor_id,
        serialize=lambda rows: Entity.serialize_list(rows, obj_type="Asset"),
    )
    metadata_descriptors_service.remove_not_allowed_metadata_for_vendor(
        "Asset",
        criterions.get("vendor_departments"),
        result["data"] if isinstance(result, dict) else result,
    )
    return result


def _apply_asset_and_tasks_criterions(
    query, criterions, assigned_to, only_user_projects=False
):
    """
    Apply the with-tasks asset filters on a query that has Entity in its
    FROM clause. The filters are: asset types only, id, project, episode
    casting and assignment to the current user. The episode casting and
    assignment filters are EXISTS subqueries. Because of this, no filter
    multiplies the result rows.
    """
    query = query.filter(entity_types_service.build_asset_type_filter())

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
            .filter(persons_service.build_assignee_filter())
            .exists()
        )
        query = query.filter(has_assigned_task)

    if only_user_projects:
        query = query.filter(
            persons_service.build_team_exists_filter(Entity.project_id)
        )

    return query


def prepare_assets_and_tasks(
    criterions=None,
    with_episode_ids=False,
    compact=False,
    only_user_projects=False,
    for_client=None,
):
    """
    Run the with-tasks queries. Return a generator that gives one asset at a
    time, in display order. If compact=True, each item is a list of values
    in the order of ASSETS_AND_TASKS_ASSET_FIELDS, not a dict. The tasks
    follow the order of ASSETS_AND_TASKS_TASK_FIELDS. This decreases the
    payload of the views with many tasks by half.

    The function uses three flat queries (assets, tasks, assignee links),
    not one Entity x Task x TaskPersonLink join. The join returned one row
    per (asset, task, assignee), with all the asset columns on each row. On
    large productions, this made most of the payload, the sort time and the
    Python dedup time.

    All the work on the database and on the request occurs before this
    function returns. The generator only formats data. Because of this, a
    streaming response can use it after the request context is closed. The full
    response is never in memory at one time.
    """
    if criterions is None:
        criterions = {}
    Episode = aliased(Entity, name="episode")
    subscription_map = subscriptions_service.get_subscriptions_for_user(
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
            only_user_projects,
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

    def apply_task_filters(query):
        return _apply_asset_and_tasks_criterions(
            query, criterions, assigned_to, only_user_projects
        )

    tasks_by_entity, build_task = entities_service.fetch_entity_task_map(
        apply_task_filters,
        subscription_map,
        ASSETS_AND_TASKS_TASK_FIELDS,
        assigned_to=assigned_to,
        compact=compact,
        for_client=for_client,
    )

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
        not_allowed_map = metadata_descriptors_service.get_not_allowed_descriptors_fields_for_vendor(
            "Asset",
            criterions["vendor_departments"],
            set(row.project_id for row in asset_rows),
        )

    def iterate():
        for row in asset_rows:
            asset_id = str(row.id)
            data = fields.serialize_value(row.data or {})
            if not_allowed_map is not None:
                data = metadata_descriptors_service.remove_not_allowed_fields_from_metadata(
                    not_allowed_map[row.project_id], data
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


def get_assets_and_tasks(
    criterions=None,
    with_episode_ids=False,
    only_user_projects=False,
    for_client=None,
):
    """
    Return all the assets for the given criterions, with the related tasks
    of each asset, as a list of dicts.
    """
    return list(
        prepare_assets_and_tasks(
            criterions,
            with_episode_ids,
            only_user_projects=only_user_projects,
            for_client=for_client,
        )
    )


def get_asset_types_for_project(project_id):
    """
    Return all the asset types of the assets of the given project.
    """
    return entity_types_service.serialize_asset_types(
        {x["entity_type_id"] for x in get_assets({"project_id": project_id})}
    )


def get_asset_types_for_episode(project_id, episode_id):
    """
    Return all the asset types of the assets that natively belong to the
    given episode. Shared and cast assets are excluded, to match the
    schedule scope.
    """
    return entity_types_service.serialize_asset_types(
        {
            asset.entity_type_id
            for asset in Entity.query.filter(
                entity_types_service.build_asset_type_filter()
            )
            .filter(Entity.project_id == project_id)
            .filter(Entity.source_id == episode_id)
            .all()
        }
    )


def get_asset_types_for_shot(shot_id):
    """
    Return all the asset types of the assets cast in the given shot.
    """
    shot = Entity.get(shot_id)
    return entity_types_service.serialize_asset_types(
        {x.entity_type_id for x in shot.entities_out}
    )


def get_asset_raw(entity_id):
    """
    Return the given asset as an active record.
    """
    try:
        entity = Entity.get(entity_id)
    except StatementError:
        raise AssetNotFoundException

    if entity is None or not entity_types_service.is_asset(entity):
        raise AssetNotFoundException

    return entity


@cache.memoize_function(120)
def get_asset(entity_id, relations=False):
    """
    Return the given asset as a dict.
    """
    return get_asset_raw(entity_id).serialize(
        obj_type="Asset", relations=relations
    )


def get_asset_by_shotgun_id(shotgun_id):
    """
    Return the asset that matches the given shotgun ID, as a dict.
    """
    assets = get_assets({"shotgun_id": shotgun_id})
    if len(assets) == 0:
        raise AssetNotFoundException
    return assets[0]


def get_raw_asset_by_shotgun_id(shotgun_id):
    """
    Return the asset that matches the given shotgun ID, as an active
    record.
    """
    asset = get_asset_by_shotgun_id(shotgun_id)
    return get_asset_raw(asset["id"])


@cache.memoize_function_single_flight(120)
def get_full_asset(asset_id):
    """
    Return the asset that has the given ID, with more data: the project
    name, the asset type name and the tasks.
    """
    assets = get_assets_and_tasks(
        {"id": asset_id}, with_episode_ids=True, for_client=False
    )
    if len(assets) == 0:
        raise AssetNotFoundException

    asset = dict(get_asset(asset_id, relations=True))
    asset_type = entity_types_service.get_asset_type(asset["entity_type_id"])
    project = Project.get(asset["project_id"])

    asset["project_name"] = project.name
    asset["asset_type_id"] = asset_type["id"]
    asset["asset_type_name"] = asset_type["name"]
    del asset["source_id"]
    del asset["nb_frames"]
    asset.update(assets[0])
    return asset


def create_asset_types(asset_type_names):
    """
    For each name, return the asset type. If the asset type does not exist,
    create it.
    """
    asset_types = []
    for asset_type_name in asset_type_names:
        asset_type = entity_types_service.get_or_create_asset_type(
            asset_type_name
        )
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
    ready_for=None,
    index=True,
):
    """
    Create a new asset from the given parameters, index it and emit an
    asset:new event. If source_id is shorter than a UUID, ignore it. A bulk
    import passes index=False and indexes all its assets at the end.
    """
    project = projects_service.get_project_raw(project_id)
    asset_type = entity_types_service.get_asset_type_raw(asset_type_id)
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
        ready_for=ready_for,
    )

    if index:
        index_service.index_asset(asset)
    events.emit(
        "asset:new",
        {"asset_id": asset.id, "asset_type": asset_type.id},
        project_id=str(project.id),
    )

    return asset.serialize(obj_type="Asset")


def update_asset(asset_id, data, index=True):
    """
    Update the given asset, drop its cache and notify the clients. A bulk
    import passes index=False and indexes all its assets at the end.
    """
    asset = get_asset_raw(asset_id)
    asset.update(data)

    if index:
        index_service.remove_asset_index(asset_id)
        index_service.index_asset(asset)
    events.emit(
        "asset:update",
        {"asset_id": asset_id, "data": data},
        project_id=str(asset.project_id),
    )
    clear_asset_cache(asset_id)

    return asset.serialize(obj_type="Asset")


def set_shared_assets(
    is_shared=True,
    project_id=None,
    asset_type_id=None,
    asset_ids=None,
    with_events=False,
):
    """
    Set is_shared on the assets that match the given project, asset type
    and asset IDs, and drop their cache. If with_events is set, emit an
    asset:update event for each asset.
    """

    query = Entity.query.filter(entity_types_service.build_asset_type_filter())

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


def get_shared_assets_used_in_project(project_id, episode_id=None, **paging):
    """
    Return the shared assets of other projects that are cast in the shots
    of the given project. If an episode is given, use only the shots of this
    episode. Canceled assets are excluded. The paging options are the ones
    of query_utils.get_paginated_results.
    """
    Shot = aliased(Entity, name="shot")
    Sequence = aliased(Entity, name="sequence")

    # Use an EXISTS clause, not joins: an asset cast in many shots
    # occurs one time, so a limit counts assets.
    casting = (
        db.session.query(EntityLink.id)
        .join(Shot, EntityLink.entity_in_id == Shot.id)
        .join(Sequence, Shot.parent_id == Sequence.id)
        .filter(EntityLink.entity_out_id == Entity.id)
        .filter(Shot.project_id == project_id)
    )
    if episode_id is not None and episode_id not in ["main", "all"]:
        casting = casting.filter(Sequence.parent_id == episode_id)

    assets = (
        Entity.query.filter(entity_types_service.build_asset_type_filter())
        .filter(Entity.is_shared == True)
        .filter(Entity.canceled != True)
        .filter(Entity.project_id != project_id)
        .filter(casting.exists())
        .order_by(Entity.name)
    )
    return query_utils.get_paginated_results(
        assets,
        serialize=lambda rows: Entity.serialize_list(rows, obj_type="Asset"),
        **paging,
    )
