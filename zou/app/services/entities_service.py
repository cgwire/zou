from sqlalchemy import cast, func, Text
from sqlalchemy.exc import IntegrityError

from zou.app.services import (
    assets_service,
    base_service,
    persons_service,
    projects_service,
    notifications_service,
    shots_service,
    edits_service,
    tasks_service,
)
from zou.app.utils import (
    date_helpers,
    cache,
    events,
    fields,
    http_cache,
    permissions,
    query as query_utils,
)

from zou.app.models.entity import Entity, EntityLink, EntityConceptLink
from zou.app.models.entity_type import EntityType
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.subscription import Subscription
from zou.app.models.task import Task, TaskPersonLink

from zou.app import db

from zou.app.exceptions import (
    PreviewFileNotFoundException,
    EntityLinkNotFoundException,
    EntityNotFoundException,
    EntityTypeNotFoundException,
)

# Entity types positioned in time, as opposed to the asset types. Their
# name doubles as the event prefix (shot:update, edit:update...), so every
# type missing from this list is reported to the clients as an asset.
TEMPORAL_ENTITY_TYPE_NAMES = [
    "Shot",
    "Sequence",
    "Scene",
    "Edit",
    "Concept",
    "ConceptFolder",
    "Episode",
]


def clear_entity_cache(entity_id):
    """
    Drop the memoized serialization and full name of given entity.
    """
    # Renaming a parent (sequence, episode) still leaves the children
    # names cached up to their TTL; only the entity's own name goes.
    entity_id = str(entity_id)
    cache.cache.delete_memoized(_get_entity_cached, entity_id)
    cache.cache.delete_memoized(get_full_entity_name, entity_id)


def _load_entities(entity_ids, *already_loaded):
    """
    Return the serialized entities for given ids, keyed by id. Entities
    present in the already loaded maps are reused, only the rest is queried.
    The maps are searched in order, so the first one wins.
    """
    entities = {}
    missing = {str(entity_id) for entity_id in entity_ids}
    for loaded in already_loaded:
        for entity_id in missing & loaded.keys():
            entities[entity_id] = loaded[entity_id]
        missing -= entities.keys()

    if missing:
        for entity in Entity.query.filter(Entity.id.in_(list(missing))).all():
            entities[str(entity.id)] = entity.serialize()
    return entities


def _collect_parent_ids(entities_map):
    """
    Return the ids of the parents of given entities, skipping the roots.
    """
    return {
        entity["parent_id"]
        for entity in entities_map.values()
        if entity["parent_id"] is not None
    }


@cache.memoize_function(1200)
def get_full_entity_name(entity_id):
    """
    Get full entity name whether it's an asset or a shot. If it's a shot
    the result is "Episode name / Sequence name / Shot name". If it's an
    asset the result is "Asset type name / Asset name".
    """
    entity = get_entity(entity_id)
    episode_id = None
    if shots_service.is_shot(entity):
        sequence = get_entity(entity["parent_id"])
        if sequence["parent_id"] is None:
            name = f"{sequence['name']} / {entity['name']}"
        else:
            episode = get_entity(sequence["parent_id"])
            episode_id = episode["id"]
            name = f"{episode['name']} / {sequence['name']} / {entity['name']}"
    elif shots_service.is_episode(entity):
        name = entity["name"]
    elif shots_service.is_sequence(entity):
        name = entity["name"]
        if entity["parent_id"] is not None:
            episode = get_entity(entity["parent_id"])
            episode_id = episode["id"]
            name = f"{episode['name']} / {entity['name']}"
    else:
        asset_type = get_entity_type(entity["entity_type_id"])
        episode_id = entity["source_id"]
        name = f"{asset_type['name']} / {entity['name']}"
    return name, episode_id, entity["preview_file_id"]


def get_full_entity_names(entity_ids):
    """
    Batch version of get_full_entity_name. Takes a list of entity IDs
    and returns a dict mapping entity_id -> (name, episode_id,
    preview_file_id). Uses 2-3 queries instead of N.
    """
    if not entity_ids:
        return {}

    unique_ids = list(set(entity_ids))

    entities_map = _load_entities(unique_ids)
    parent_ids = _collect_parent_ids(entities_map)
    parents_map = _load_entities(parent_ids, entities_map)
    # Grandparents are the episodes of the sequences.
    grandparent_ids = _collect_parent_ids(parents_map)
    grandparents_map = _load_entities(
        grandparent_ids, entities_map, parents_map
    )

    all_entities = {}
    all_entities.update(grandparents_map)
    all_entities.update(parents_map)
    all_entities.update(entities_map)

    # Get type IDs for classification
    shot_type = shots_service.get_shot_type()
    episode_type = shots_service.get_episode_type()
    sequence_type = shots_service.get_sequence_type()

    # Anything that is not a shot, an episode or a sequence is an asset, so
    # its entity type has to be resolved to build the name.
    asset_type_ids = {
        entity["entity_type_id"]
        for entity in entities_map.values()
        if str(entity["entity_type_id"])
        not in (shot_type["id"], episode_type["id"], sequence_type["id"])
    }
    asset_types_map = {}
    if asset_type_ids:
        asset_types_map = {
            str(entity_type.id): entity_type.serialize()
            for entity_type in EntityType.query.filter(
                EntityType.id.in_(list(asset_type_ids))
            ).all()
        }

    # Build names
    result = {}
    for eid in unique_ids:
        str_eid = str(eid)
        entity = entities_map.get(str_eid)
        if entity is None:
            continue

        episode_id = None
        etype = str(entity["entity_type_id"])

        if etype == shot_type["id"]:
            parent = all_entities.get(str(entity["parent_id"]))
            if parent is None:
                name = entity["name"]
            elif parent["parent_id"] is None:
                name = f"{parent['name']} / {entity['name']}"
            else:
                grandparent = all_entities.get(str(parent["parent_id"]))
                if grandparent:
                    episode_id = grandparent["id"]
                    name = (
                        f"{grandparent['name']} / {parent['name']} / "
                        f"{entity['name']}"
                    )
                else:
                    name = f"{parent['name']} / {entity['name']}"
        elif etype == episode_type["id"]:
            name = entity["name"]
        elif etype == sequence_type["id"]:
            if entity["parent_id"] is None:
                name = entity["name"]
            else:
                parent = all_entities.get(str(entity["parent_id"]))
                if parent:
                    episode_id = parent["id"]
                    name = f"{parent['name']} / {entity['name']}"
                else:
                    name = entity["name"]
        else:
            asset_type = asset_types_map.get(str(entity["entity_type_id"]))
            episode_id = entity["source_id"]
            if asset_type:
                name = f"{asset_type['name']} / {entity['name']}"
            else:
                name = entity["name"]

        result[str_eid] = name, episode_id, entity["preview_file_id"]

    return result


def clear_entity_type_cache(entity_type_id):
    """
    Drop the memoized serializations of given entity type. The by-name
    lookups are flushed whole, since the name is not known here.
    """
    cache.cache.delete_memoized(_get_entity_type_cached, str(entity_type_id))
    cache.cache.delete_memoized(get_entity_type_by_name)
    cache.cache.delete_memoized(get_entity_type_by_name_or_not_found)


def get_temporal_entity_type_by_name(name):
    """
    Return the entity type matching given name, creating it if needed. A
    cached None (the type did not exist yet when it was first looked up) is
    dropped and looked up again.
    """
    entity_type = get_entity_type_by_name(name)
    if entity_type is None:
        cache.cache.delete_memoized(get_entity_type_by_name, name)
        entity_type = get_entity_type_by_name(name)
    return entity_type


def is_edit(entity):
    """
    Return True if given entity dict has 'Edit' as entity type.
    """
    edit_type = get_temporal_entity_type_by_name("Edit")
    return str(entity["entity_type_id"]) == edit_type["id"]


@cache.memoize_function(240)
def _get_entity_type_cached(entity_type_id):
    return base_service.get_instance(
        EntityType, entity_type_id, EntityTypeNotFoundException
    ).serialize()


def get_entity_type(entity_type_id):
    """
    Return an entity type matching given id, as a dict. Raises an exception
    if nothing is found.

    The id is normalised before it reaches the memoization, which keys on
    the argument: callers hold it as a UUID read off a row as often as they
    hold the string form, and the two must not be two cache entries.
    """
    return _get_entity_type_cached(str(entity_type_id))


@cache.memoize_function(240)
def get_entity_type_by_name(name):
    """
    Return entity type maching *name*. If it doesn't exist, it creates it.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        entity_type = EntityType.create(name=name)
    return entity_type.serialize()


@cache.memoize_function(240)
def get_entity_type_by_name_or_not_found(name):
    """
    Return entity type maching *name*. If it doesn't exist, it raises.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        raise EntityTypeNotFoundException
    return entity_type.serialize()


def find_entity_raw(**lookup):
    """
    Return the entity matching given columns (name, project_id,
    entity_type_id, parent_id...) as an active record, or None.
    """
    return Entity.get_by(**lookup)


def get_entity_raw(entity_id):
    """
    Return an entity type matching given id, as an active record. Raises an
    exception if nothing is found.
    """
    return base_service.get_instance(
        Entity, entity_id, EntityNotFoundException
    )


@cache.memoize_function(120)
def _get_entity_cached(entity_id):
    return base_service.get_instance(
        Entity, entity_id, EntityNotFoundException
    ).serialize()


def get_entity(entity_id):
    """
    Return an entity type matching given id, as a dict. Raises an exception if
    nothing is found.

    The id is normalised before it reaches the memoization: see
    get_entity_type.
    """
    return _get_entity_cached(str(entity_id))


def update_entity_preview(entity_id, preview_file_id):
    """
    Update given entity main preview. If entity or preview is not found, it
    raises an exception.
    """
    entity = Entity.get(entity_id)
    if entity is None:
        raise EntityNotFoundException

    entity_id = str(entity.id)
    preview_file = PreviewFile.get(preview_file_id)
    if preview_file is None:
        raise PreviewFileNotFoundException

    try:
        entity.update({"preview_file_id": preview_file.id})
    except IntegrityError:
        raise PreviewFileNotFoundException
    clear_entity_cache(entity_id)
    events.emit(
        "preview-file:set-main",
        {"entity_id": entity_id, "preview_file_id": preview_file_id},
        project_id=str(entity.project_id),
    )
    entity_type = EntityType.get(entity.entity_type_id)
    entity_type_name = "asset"
    if entity_type.name in TEMPORAL_ENTITY_TYPE_NAMES:
        entity_type_name = entity_type.name.lower()
    events.emit(
        f"{entity_type_name}:update",
        {f"{entity_type_name}_id": entity_id},
        project_id=str(entity.project_id),
    )
    assets_service.clear_asset_cache(entity_id)
    edits_service.clear_edit_cache(entity_id)
    shots_service.clear_shot_cache(entity_id)
    shots_service.clear_episode_cache(entity_id)
    shots_service.clear_sequence_cache(entity_id)
    return entity.serialize()


def get_for_entity_from_task(task):
    """
    Return the entity type name for given task. All asset types are returned
    as "Asset".
    """
    entity = get_entity(task["entity_id"])
    entity_type = get_entity_type(entity["entity_type_id"])
    for_entity = entity_type["name"]
    if for_entity.lower() not in [
        "shot",
        "sequence",
        "episode",
        "edit",
        "concept",
    ]:
        for_entity = "Asset"
    return for_entity


def get_entities_for_project(
    project_id,
    entity_type_id,
    obj_type="Entity",
    episode_id=None,
    only_assigned=False,
):
    """
    Retrieve all entities related to given project of which entity is entity
    type.
    """
    query = (
        Entity.query.filter(Entity.entity_type_id == entity_type_id)
        .filter(Entity.project_id == project_id)
        .order_by(Entity.name)
    )

    if episode_id is not None:
        query = query.filter(Entity.parent_id == episode_id)

    if only_assigned:
        query = query.outerjoin(Task).filter(
            persons_service.build_assignee_filter()
        )
    result = query.all()
    return Entity.serialize_list(result, obj_type=obj_type)


def get_entity_links_for_project(
    project_id,
    page=None,
    limit=None,
    cursor_created_at=None,
):
    """
    Retrieve entity links for given project.
    """
    query = EntityLink.query.filter(Entity.project_id == project_id).join(
        Entity, EntityLink.entity_in_id == Entity.id
    )

    results = []
    if page is not None and page > 0:
        if limit < 1:
            limit = None
        query = query.order_by(EntityLink.created_at, EntityLink.id)
        results = query_utils.get_paginated_results(query, page, limit=limit)
    elif cursor_created_at is not None:
        if limit < 1:
            limit = None
        created_at = date_helpers.get_datetime_from_string(
            cursor_created_at, milliseconds=True
        )
        results = query_utils.get_cursor_results(
            EntityLink, query, created_at, limit=limit
        )
    else:
        query = query.order_by(EntityLink.created_at, EntityLink.id)
        if limit is not None and limit > 0:
            query = query.limit(limit)
        for entity_link in query.all():
            results.append(
                {
                    "id": entity_link.id,
                    "entity_in_id": entity_link.entity_in_id,
                    "entity_out_id": entity_link.entity_out_id,
                    "nb_occurences": entity_link.nb_occurences,
                    "label": entity_link.label,
                    "data": entity_link.data,
                    "created_at": date_helpers.get_date_string(
                        entity_link.created_at, milliseconds=True
                    ),
                    "type": "EntityLink",
                }
            )
    return results


# Builders for each task field of the with-tasks views. Every view picks
# its exact field list so its response shape stays unchanged; is_subscribed
# and assignees are always added by build_task.
_TASK_FIELD_BUILDERS = {
    "id": lambda row: row.id,
    "entity_id": lambda row: row.entity_id,
    "task_type_id": lambda row: row.task_type_id,
    "task_status_id": lambda row: row.task_status_id,
    "priority": lambda row: row.priority or 0,
    "estimation": lambda row: row.estimation,
    "duration": lambda row: row.duration,
    "retake_count": lambda row: row.retake_count,
    "real_start_date": lambda row: fields.serialize_datetime(
        row.real_start_date
    ),
    "end_date": lambda row: fields.serialize_datetime(row.end_date),
    "start_date": lambda row: fields.serialize_datetime(row.start_date),
    "due_date": lambda row: fields.serialize_datetime(row.due_date),
    "done_date": lambda row: fields.serialize_datetime(row.done_date),
    "last_comment_date": lambda row: fields.serialize_datetime(
        row.last_comment_date
    ),
    "last_preview_file_id": lambda row: row.last_preview_file_id,
    "nb_assets_ready": lambda row: row.nb_assets_ready,
    "difficulty": lambda row: row.difficulty,
    "nb_drawings": lambda row: row.nb_drawings,
    "data": lambda row: fields.serialize_value(row.data),
}

ENTITIES_AND_TASKS_TASK_FIELDS = [
    "id",
    "estimation",
    "entity_id",
    "end_date",
    "due_date",
    "done_date",
    "duration",
    "last_comment_date",
    "last_preview_file_id",
    "priority",
    "real_start_date",
    "retake_count",
    "start_date",
    "difficulty",
    "task_status_id",
    "task_type_id",
    "data",
]


def fetch_entity_task_map(
    apply_filters,
    subscription_map,
    task_fields,
    assigned_to=False,
    compact=False,
):
    """
    Shared core of the get_*_and_tasks views: fetch the tasks and the
    assignee links of the entities selected by apply_filters (a callable
    adding entity-scoped filters and joins to a query whose FROM clause
    contains Entity) with two narrow flat queries, then group them.

    Returns (tasks_by_entity, build_task): task rows grouped by entity id
    (uuid as text) and a builder producing task dicts restricted to
    task_fields, so every view keeps its exact response shape; with
    compact=True the builder produces a list of values in the order of
    task_fields instead. With assigned_to=True only the tasks assigned to
    the current user are fetched.
    """
    task_query = apply_filters(
        Task.query.join(Entity, Task.entity_id == Entity.id)
    ).with_entities(
        # uuid::text in SQL: casting uuids per task row in Python shows
        # up in profiles on task-heavy productions.
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
        Task.nb_assets_ready,
        Task.difficulty,
        Task.nb_drawings,
        Task.data,
    )
    if assigned_to:
        task_query = task_query.filter(persons_service.build_assignee_filter())
    task_rows = task_query.all()

    link_query = apply_filters(
        db.session.query(TaskPersonLink)
        .join(Task, TaskPersonLink.task_id == Task.id)
        .join(Entity, Task.entity_id == Entity.id)
    ).with_entities(
        cast(TaskPersonLink.task_id, Text),
        cast(TaskPersonLink.person_id, Text),
    )
    if assigned_to:
        link_query = link_query.filter(persons_service.build_assignee_filter())

    assignees_by_task = {}
    for task_id, person_id in link_query.all():
        if person_id:
            assignees_by_task.setdefault(task_id, []).append(person_id)

    tasks_by_entity = {}
    for row in task_rows:
        tasks_by_entity.setdefault(row.entity_id, []).append(row)

    builders = [
        (
            name,
            _TASK_FIELD_BUILDERS.get(name)
            or {
                "is_subscribed": lambda row: subscription_map.get(
                    row.id, False
                ),
                "assignees": lambda row: assignees_by_task.get(row.id, []),
            }[name],
        )
        for name in task_fields
    ]

    if compact:

        def build_task(row):
            return [builder(row) for _, builder in builders]

    else:

        def build_task(row):
            task = {name: builder(row) for name, builder in builders}
            task.setdefault(
                "is_subscribed", subscription_map.get(row.id, False)
            )
            task.setdefault("assignees", assignees_by_task.get(row.id, []))
            return task

    return tasks_by_entity, build_task


def get_project_board_fingerprint(project_id, user_id):
    """
    Cheap change signal for the with-tasks boards of given project. It
    covers everything those payloads embed: the entities of the project
    (parents' names included, a sequence is an entity too), the tasks
    (assigning saves the task), the project row and the entity type
    names, plus the caller's subscriptions. Five scalar reads, orders of
    magnitude cheaper than the boards they guard.
    """
    signals = [
        Entity.query.with_entities(
            func.max(Entity.updated_at), func.count(Entity.id)
        )
        .filter(Entity.project_id == project_id)
        .one(),
        Task.query.with_entities(
            func.max(Task.updated_at), func.count(Task.id)
        )
        .filter(Task.project_id == project_id)
        .one(),
        EntityType.query.with_entities(
            func.max(EntityType.updated_at), func.count(EntityType.id)
        ).one(),
        Subscription.query.with_entities(
            func.max(Subscription.updated_at), func.count(Subscription.id)
        )
        .filter(Subscription.person_id == user_id)
        .one(),
    ]
    project_updated_at = (
        Project.query.with_entities(Project.updated_at)
        .filter(Project.id == project_id)
        .scalar()
    )
    parts = [f"{updated_at}:{count}" for updated_at, count in signals]
    parts.append(str(project_updated_at))
    return "|".join(parts)


def get_project_board_etag(criterions):
    """
    Build the conditional GET validator for a with-tasks board, or None
    when the request is not scoped to one project. Hashes the board
    fingerprint with the caller, its effective role and the resolved
    criterions (vendor scoping included). Call it after the permission
    checks: the effective role needs the project resolved.
    """
    project_id = criterions.get("project_id")
    if project_id is None:
        return None
    user_id = persons_service.get_current_user()["id"]
    return http_cache.build_etag(
        get_project_board_fingerprint(project_id, user_id),
        user_id,
        permissions.get_effective_role(),
        str(sorted(criterions.items())),
    )


def get_entities_and_tasks(criterions=None):
    """
    Get all entities for given criterions with related tasks for each
    entity, as a list of dicts.
    """
    if criterions is None:
        criterions = {}

    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None),
        criterions.get("entity_type_id", None),
    )

    def apply_filters(query):
        if "entity_type_id" in criterions:
            query = query.filter(
                Entity.entity_type_id == criterions["entity_type_id"]
            )
        if "project_id" in criterions:
            query = query.filter(Entity.project_id == criterions["project_id"])
        # "all" is the cross-episode pseudo-episode Kitsu uses for its
        # production-wide views: no episode filter, like shots_service.
        if "episode_id" in criterions and criterions["episode_id"] != "all":
            query = query.filter(Entity.parent_id == criterions["episode_id"])
        if "entity_ids" in criterions:
            query = query.filter(Entity.id.in_(criterions["entity_ids"]))
        return query

    entity_rows = (
        apply_filters(Entity.query)
        .with_entities(
            cast(Entity.id, Text).label("id"),
            Entity.name,
            Entity.status,
            cast(Entity.parent_id, Text).label("parent_id"),
            Entity.description,
            Entity.data,
            cast(Entity.preview_file_id, Text).label("preview_file_id"),
            Entity.canceled,
        )
        .all()
    )

    tasks_by_entity, build_task = fetch_entity_task_map(
        apply_filters, subscription_map, ENTITIES_AND_TASKS_TASK_FIELDS
    )

    assigned_to = criterions.get("assigned_to")
    entities = []
    for row in entity_rows:
        data = row.data or {}
        status = "running"
        if row.status is not None:
            status = str(row.status.code)
        tasks = [
            build_task(task_row)
            for task_row in tasks_by_entity.get(row.id, ())
        ]
        if assigned_to is not None:
            tasks = [
                task for task in tasks if assigned_to in task["assignees"]
            ]
        entities.append(
            {
                "id": row.id,
                "name": row.name,
                "status": status,
                "episode_id": str(row.parent_id),
                "description": row.description,
                "frame_in": data.get("frame_in", None),
                "frame_out": data.get("frame_out", None),
                "fps": data.get("fps", None),
                "preview_file_id": row.preview_file_id or "",
                "canceled": row.canceled,
                "data": fields.serialize_value(data),
                "tasks": tasks,
            }
        )
    return entities


def get_entity_tasks(entity):
    """
    Get all tasks for a given entity.
    """
    entity_type = get_entity_type(entity_type_id=entity["entity_type_id"])
    entity_type_name = entity_type["name"]
    if assets_service.is_asset_type(entity_type):
        entity_type_name = "Asset"
    get_tasks = getattr(
        tasks_service, "get_tasks_for_" + entity_type_name.lower()
    )
    return get_tasks(entity["id"])


def get_entity_link(link_id):
    """
    Return the entity link matching given id, as a dict. Raises an exception
    if nothing is found.
    """
    link = EntityLink.get_by(id=link_id)
    if link is None:
        raise EntityLinkNotFoundException
    return link.serialize()


def remove_entity_link(link_id):
    """
    Delete the entity link matching given id and return it.
    """
    link = EntityLink.get_by(id=link_id)
    if link is None:
        raise EntityLinkNotFoundException
    link.delete()
    return link.serialize()


def get_not_allowed_descriptors_fields_for_vendor(
    entity_type="Asset", departments=None, projects_ids=None
):
    """
    Return, per project, the metadata field names a vendor of given
    departments must not see: the descriptors restricted to departments they
    do not belong to.
    """
    if departments is None:
        departments = []
    if projects_ids is None:
        projects_ids = []
    not_allowed_descriptors_field_names = {}
    for project_id in projects_ids:
        not_allowed_descriptors_field_names[project_id] = [
            descriptor["field_name"]
            for descriptor in projects_service.get_metadata_descriptors(
                project_id
            )
            if descriptor["entity_type"] == entity_type
            and descriptor["departments"] != []
            and len(set(departments) & set(descriptor["departments"])) == 0
        ]
    return not_allowed_descriptors_field_names


def remove_not_allowed_fields_from_metadata(
    not_allowed_descriptors_field_names=None, data=None
):
    """
    Return given metadata without the fields the caller must not see.
    """
    if not_allowed_descriptors_field_names is None:
        not_allowed_descriptors_field_names = []
    if data is None:
        data = {}
    return {
        key: value
        for key, value in data.items()
        if key not in not_allowed_descriptors_field_names
    }


def remove_not_allowed_metadata_for_vendor(
    entity_type, departments, entities, project_id=None
):
    """
    Strip from a serialized listing the metadata a vendor of given departments
    must not see, in place. No departments means nothing to narrow down.

    The listings that carry the tasks pick their columns one by one and mask
    them while they build their rows. These hand back whole serialized
    entities, so the restricted descriptors come along unless they are taken
    out here. Some of those listings drop the project on the way, hence the
    fallback the caller passes in.
    """
    if departments is None:
        return entities
    not_allowed_map = get_not_allowed_descriptors_fields_for_vendor(
        entity_type,
        departments,
        set(entity.get("project_id") or project_id for entity in entities),
    )
    for entity in entities:
        entity["data"] = remove_not_allowed_fields_from_metadata(
            not_allowed_map[entity.get("project_id") or project_id],
            entity["data"],
        )
    return entities


def get_linked_entities_with_tasks(entity_id):
    """
    Return all entities and their tasks linked to given entity.
    """
    entities_in = (
        db.session.query(EntityConceptLink.entity_in_id)
        .filter(EntityConceptLink.entity_out_id == entity_id)
        .distinct()
    )

    entity_map = {}
    task_map = {}

    query = (
        Entity.query.join(Project, Project.id == Entity.project_id)
        .outerjoin(Task, Task.entity_id == Entity.id)
        .outerjoin(TaskPersonLink)
        .join(EntityType)
        .add_columns(
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
            Task.assigner_id,
            TaskPersonLink.person_id,
            Project.id,
            Project.name,
            EntityType.name,
        )
        .filter(Entity.id.in_(entities_in))
    )
    query_result = query.all()

    for (
        entity,
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
        task_assigner_id,
        person_id,
        project_id,
        project_name,
        entity_type_name,
    ) in query_result:
        entity_id = str(entity.id)

        if entity_id not in entity_map:
            data = fields.serialize_value(entity.data or {})

            entity_map[entity_id] = fields.serialize_dict(
                {
                    "canceled": entity.canceled,
                    "data": data,
                    "description": entity.description,
                    "entity_type_id": entity.entity_type_id,
                    "fps": data.get("fps", None),
                    "frame_in": data.get("frame_in", None),
                    "frame_out": data.get("frame_out", None),
                    "id": entity.id,
                    "name": entity.name,
                    "nb_frames": entity.nb_frames,
                    "parent_id": entity.parent_id,
                    "preview_file_id": entity.preview_file_id or None,
                    "project_id": project_id,
                    "project_name": project_name,
                    "source_id": entity.source_id,
                    "nb_entities_out": entity.nb_entities_out,
                    "is_casting_standby": entity.is_casting_standby,
                    "tasks": [],
                    "entity_concept_links": entity.entity_concept_links,
                    "type": (
                        entity_type_name
                        if entity_type_name in TEMPORAL_ENTITY_TYPE_NAMES
                        else "Asset"
                    ),
                    "updated_at": entity.updated_at,
                    "created_at": entity.created_at,
                    "created_by": entity.created_by,
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
                        "entity_id": entity_id,
                        "estimation": task_estimation,
                        "last_comment_date": task_last_comment_date,
                        "nb_assets_ready": task_nb_assets_ready,
                        "priority": task_priority or 0,
                        "real_start_date": task_real_start_date,
                        "retake_count": task_retake_count,
                        "start_date": task_start_date,
                        "task_status_id": task_status_id,
                        "task_type_id": task_type_id,
                        "assigner_id": task_assigner_id,
                        "assignees": [],
                    }
                )
                task_map[task_id] = task_dict
                entity_dict = entity_map[entity_id]
                entity_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(entity_map.values())
