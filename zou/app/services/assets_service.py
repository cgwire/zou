from sqlalchemy import or_
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import aliased

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
from zou.app.models.task import Task
from zou.app.models.asset_instance import AssetInstance
from zou.app.models.task import assignees_table

from zou.app.services import (
    base_service,
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
    cache.cache.delete_memoized(get_asset_with_relations, asset_id)
    cache.cache.delete_memoized(get_full_asset, asset_id)


def clear_asset_type_cache():
    cache.cache.delete_memoized(get_asset_types)


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


def get_assets(criterions={}):
    """
    Get all assets for given criterions.
    """
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
    return EntityType.serialize_list(result, obj_type="Asset")


def get_all_raw_assets():
    """
    Get all assets from the database.
    """
    query = Entity.query.filter(build_asset_type_filter())
    return query.all()


def get_full_assets(criterions={}):
    """
    Get all assets for given criterions with additional informations: project
    name and asset type name.
    """
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


def get_assets_and_tasks(criterions={}, page=1, with_episode_ids=False):
    """
    Get all assets for given criterions with related tasks for each asset.
    """
    asset_map = {}
    task_map = {}
    Episode = aliased(Entity, name="episode")
    subscription_map = notifications_service.get_subscriptions_for_user(
        criterions.get("project_id", None), None
    )

    query = (
        Entity.query.filter(build_asset_type_filter())
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .outerjoin(Task)
        .outerjoin(assignees_table)
    )

    tasks_query = query.add_columns(
        EntityType.name,
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
        assignees_table.columns.person,
    ).order_by(EntityType.name, Entity.name)

    if "id" in criterions:
        tasks_query = tasks_query.filter(Entity.id == criterions["id"])

    if "project_id" in criterions:
        tasks_query = tasks_query.filter(
            Entity.project_id == criterions["project_id"]
        )

    if "episode_id" in criterions:
        episode_id = criterions["episode_id"]
        if episode_id == "main":
            tasks_query = tasks_query.filter(Entity.source_id == None)
        elif episode_id != "all":
            tasks_query = tasks_query.outerjoin(
                EntityLink, EntityLink.entity_out_id == Entity.id
            )
            tasks_query = tasks_query.filter(
                or_(
                    Entity.source_id == episode_id,
                    EntityLink.entity_in_id == episode_id,
                )
            )

    if "assigned_to" in criterions:
        tasks_query = tasks_query.filter(user_service.build_assignee_filter())
        del criterions["assigned_to"]

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
        for link in episode_links_query.all():
            if str(link.entity_out_id) not in cast_in_episode_ids:
                cast_in_episode_ids[str(link.entity_out_id)] = []
            cast_in_episode_ids[str(link.entity_out_id)].append(
                str(link.entity_in_id)
            )

    query_result = tasks_query.all()

    if "vendor_departments" in criterions:
        not_allowed_descriptors_field_names = (
            entities_service.get_not_allowed_descriptors_fields_for_vendor(
                "Asset",
                criterions["vendor_departments"],
                set(asset[0].project_id for asset in query_result),
            )
        )

    for (
        asset,
        entity_type_name,
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
        person_id,
    ) in query_result:
        if asset.source_id is None:
            source_id = ""
        else:
            source_id = str(asset.source_id)

        asset_id = str(asset.id)

        if asset_id not in asset_map:
            data = fields.serialize_value(asset.data or {})
            if "vendor_departments" in criterions:
                data = (
                    entities_service.remove_not_allowed_fields_from_metadata(
                        not_allowed_descriptors_field_names[asset.project_id],
                        data,
                    )
                )

            asset_map[asset_id] = {
                "id": asset_id,
                "name": asset.name,
                "preview_file_id": str(asset.preview_file_id or ""),
                "description": asset.description,
                "asset_type_name": entity_type_name,
                "asset_type_id": str(asset.entity_type_id),
                "canceled": asset.canceled,
                "ready_for": str(asset.ready_for),
                "episode_id": source_id,
                "casting_episode_ids": cast_in_episode_ids.get(asset_id, []),
                "is_casting_standby": asset.is_casting_standby,
                "data": data,
                "tasks": [],
            }

        if task_id is not None:
            task_id = str(task_id)
            if task_id not in task_map:
                task_dict = {
                    "id": task_id,
                    "due_date": fields.serialize_value(task_due_date),
                    "done_date": fields.serialize_value(task_done_date),
                    "duration": task_duration,
                    "entity_id": asset_id,
                    "estimation": task_estimation,
                    "end_date": fields.serialize_value(task_end_date),
                    "is_subscribed": subscription_map.get(task_id, False),
                    "last_comment_date": fields.serialize_value(
                        task_last_comment_date
                    ),
                    "priority": task_priority or 0,
                    "real_start_date": fields.serialize_value(
                        task_real_start_date
                    ),
                    "retake_count": task_retake_count,
                    "start_date": fields.serialize_value(task_start_date),
                    "task_status_id": str(task_status_id),
                    "task_type_id": str(task_type_id),
                    "assignees": [],
                }
                task_map[task_id] = task_dict
                asset_dict = asset_map[asset_id]
                asset_dict["tasks"].append(task_dict)

            if person_id:
                task_map[task_id]["assignees"].append(str(person_id))

    return list(asset_map.values())


@cache.memoize_function(240)
def get_asset_types(criterions={}):
    """
    Retrieve all asset types available.
    """
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    query = query_utils.apply_criterions_to_db_query(Entity, query, criterions)
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
def get_asset(entity_id):
    """
    Return a given asset as a dict.
    """
    return get_asset_raw(entity_id).serialize(obj_type="Asset")


@cache.memoize_function(120)
def get_asset_with_relations(entity_id):
    """
    Return a given asset as a dict.
    """
    return get_asset_raw(entity_id).serialize(obj_type="Asset", relations=True)


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


@cache.memoize_function(120)
def get_full_asset(asset_id):
    """
    Return asset matching given id with additional information (project name,
    asset type name and tasks).
    """
    assets = get_assets_and_tasks({"id": asset_id}, with_episode_ids=True)
    if len(assets) > 0:
        asset = get_asset_with_relations(asset_id)
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

        events.emit(
            "asset-type:new", {"name": asset_type.name, "id": asset_type.id}
        )

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
    return str(entity_type.id) not in get_temporal_type_ids()


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
    else:
        from zou.app.services import tasks_service

        tasks = Task.query.filter_by(entity_id=asset_id).all()
        for task in tasks:
            deletion_service.remove_task(task.id, force=True)
            tasks_service.clear_task_cache(str(task.id))
        asset.delete()
        clear_asset_cache(str(asset_id))
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
