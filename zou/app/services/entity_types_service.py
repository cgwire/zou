from sqlalchemy import func
from sqlalchemy.exc import StatementError

from zou.app import db
from zou.app.exceptions import (
    AssetTypeNotFoundException,
    EntityTypeNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.services import base_service
from zou.app.utils import cache, events, query as query_utils


@cache.memoize_function(1200)
def get_episode_type():
    """
    Return the Episode entity type.
    """
    return get_temporal_entity_type_by_name("Episode")


@cache.memoize_function(1200)
def get_sequence_type():
    """
    Return the Sequence entity type.
    """
    return get_temporal_entity_type_by_name("Sequence")


@cache.memoize_function(1200)
def get_shot_type():
    """
    Return the Shot entity type.
    """
    return get_temporal_entity_type_by_name("Shot")


@cache.memoize_function(1200)
def get_scene_type():
    """
    Return the Scene entity type.
    """
    return get_temporal_entity_type_by_name("Scene")


def is_shot(entity):
    """
    Return True if the entity type of the given entity is 'Shot'.
    """
    shot_type = get_shot_type()
    return str(entity["entity_type_id"]) == shot_type["id"]


def is_scene(entity):
    """
    Return True if the entity type of the given entity is 'Scene'.
    """
    scene_type = get_scene_type()
    return str(entity["entity_type_id"]) == scene_type["id"]


def is_sequence(entity):
    """
    Return True if the entity type of the given entity is 'Sequence'.
    """
    sequence_type = get_sequence_type()
    return str(entity["entity_type_id"]) == sequence_type["id"]


def is_episode(entity):
    """
    Return True if the entity type of the given entity is 'Episode'.
    """
    episode_type = get_episode_type()
    return str(entity["entity_type_id"]) == episode_type["id"]


def get_base_entity_type_name(entity_dict):
    """
    Return the entity type name of the given entity, as the API uses it:
    Shot, Sequence, Episode, Edit, Scene, Concept or ConceptFolder. For
    all other entities, return Asset.
    """
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
    elif is_concept(entity_dict):
        type_name = "Concept"
    elif is_concept_folder(entity_dict):
        type_name = "ConceptFolder"

    return type_name


@cache.memoize_function(1200)
def get_edit_type():
    """
    Return the Edit entity type.
    """
    return get_temporal_entity_type_by_name("Edit")


def clear_asset_type_cache(asset_type_id=None):
    """
    Remove the memoized asset type list and all the memoized asset types.
    If an asset type is given, also remove its entity type cache.
    """
    if asset_type_id is not None:
        clear_entity_type_cache(asset_type_id)
    cache.cache.delete_memoized(get_all_asset_types)
    # get_asset_type contains the task types of the workflow. After an
    # edit, it must not return the previous value until the TTL ends.
    cache.cache.delete_memoized(get_asset_type)


def get_temporal_type_ids():
    """
    Return the IDs of the entity types that are not asset types. These are
    the types that have a position in time (shot, sequence, episode, edit,
    scene, concept) and the folders that contain the concepts.
    """
    shot_type = get_shot_type()
    scene_type = get_scene_type()
    sequence_type = get_sequence_type()
    episode_type = get_episode_type()
    edit_type = get_edit_type()
    concept_type = get_concept_type()
    concept_folder_type = get_concept_folder_type()

    return [
        shot_type["id"],
        sequence_type["id"],
        episode_type["id"],
        edit_type["id"],
        scene_type["id"],
        concept_type["id"],
        concept_folder_type["id"],
    ]


def build_asset_type_filter():
    """
    Return a query filter that keeps only the entities that are assets.
    The type of these entities is not in get_temporal_type_ids.
    """
    ids_to_exclude = get_temporal_type_ids()
    return ~Entity.entity_type_id.in_(ids_to_exclude)


def build_entity_type_asset_type_filter():
    """
    Return a query filter that keeps only the entity types that are asset
    types. These types are not in get_temporal_type_ids.
    """
    ids_to_exclude = get_temporal_type_ids()
    return ~EntityType.id.in_(ids_to_exclude)


def get_asset_types(criterions=None):
    """
    Return all the available asset types. The cache keeps only the result
    without criterions. Criterion dicts change for each request, and their
    cache entries were not used again.
    """
    if not criterions:
        return get_all_asset_types()
    criterions = dict(criterions)
    project_id = criterions.pop("project_id", None)
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    if project_id is not None:
        # An asset type is not part of a production: a production contains
        # assets of that type. The criterion is a membership test, not a
        # column of the queried table. Thus the generic criterion helper
        # cannot apply it.
        query = query.filter(
            EntityType.id.in_(
                db.session.query(Entity.entity_type_id).filter(
                    Entity.project_id == project_id
                )
            )
        )
    # Build the filters on EntityType, the queried table. On Entity, the
    # helper makes a cross join of the two tables. Then the criteria
    # filter nothing or match nothing.
    query = query_utils.apply_criterions_to_db_query(
        EntityType, query, criterions
    )
    return EntityType.serialize_list(
        query.all(), obj_type="AssetType", relations=True
    )


@cache.memoize_function(240)
def get_all_asset_types():
    """
    Return all the asset types, without criterions.
    """
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    return EntityType.serialize_list(
        query.all(), obj_type="AssetType", relations=True
    )


def serialize_asset_types(asset_type_ids):
    """
    Return the serialized asset types that have the given IDs. If there
    are no IDs, do not query the database.
    """
    result = []
    if len(asset_type_ids) > 0:
        result = EntityType.query.filter(
            EntityType.id.in_(list(asset_type_ids))
        ).all()
    return EntityType.serialize_list(result, obj_type="AssetType")


def get_asset_type_raw(asset_type_id):
    """
    Return the given asset type as an active record.
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
    Return the given asset type as a dict.
    """
    return get_asset_type_raw(asset_type_id).serialize(
        obj_type="AssetType", relations=True
    )


def find_asset_type_by_name(name):
    """
    Return the asset type that has the given name as an active record. If
    there is no such asset type, return None.

    The match is case insensitive. The asset type creation route also
    refuses a name that exists in a different case. The temporal types
    are resolved first to make sure that they exist before the search.
    Thus a name like Shot is a temporal type, not an asset type.
    """
    temporal_type_ids = get_temporal_type_ids()
    asset_type = EntityType.query.filter(
        func.lower(EntityType.name) == name.lower()
    ).first()
    if asset_type is not None and str(asset_type.id) in temporal_type_ids:
        raise WrongParameterException(f"{name} is not an asset type")
    return asset_type


def get_or_create_asset_type(name):
    """
    Return the asset type that has the given name as a dict. If it does
    not exist, create it and emit an asset-type:new event. If the name is
    the name of a temporal type, raise WrongParameterException.
    """
    asset_type = find_asset_type_by_name(name)
    if asset_type is None:
        asset_type = EntityType.create(name=name)
        clear_asset_type_cache()
        events.emit("asset-type:new", {"asset_type_id": asset_type.id})

    return asset_type.serialize(obj_type="AssetType")


def is_asset(entity):
    """
    Return True if the given entity (an active record) is an asset. The
    type of an asset is not a temporal type (shot, sequence, edit...).
    """
    return str(entity.entity_type_id) not in get_temporal_type_ids()


def is_asset_dict(entity):
    """
    Return True if the given entity (a dict) is an asset. The type of an
    asset is not a temporal type.
    """
    return str(entity["entity_type_id"]) not in get_temporal_type_ids()


def is_asset_type(entity_type):
    """
    Return True if the given entity type (a dict or an active record) is
    an asset type. An asset type is not a temporal type.
    """
    entity_type_id = ""
    if isinstance(entity_type, dict):
        entity_type_id = entity_type.get("id", "")
    else:
        entity_type_id = str(entity_type.id)
    return entity_type_id not in get_temporal_type_ids()


@cache.memoize_function(1200)
def get_concept_type():
    """
    Return the Concept entity type.
    """
    return get_temporal_entity_type_by_name("Concept")


def is_concept(entity):
    """
    Return True if the entity type of the given entity is 'Concept'.
    """
    concept_type = get_concept_type()
    return str(entity["entity_type_id"]) == concept_type["id"]


@cache.memoize_function(1200)
def get_concept_folder_type():
    """
    Return the ConceptFolder entity type.
    """
    return get_temporal_entity_type_by_name("ConceptFolder")


def is_concept_folder(entity):
    """
    Return True if the entity type of the given entity is 'ConceptFolder'.
    """
    concept_folder_type = get_concept_folder_type()
    return str(entity["entity_type_id"]) == concept_folder_type["id"]


def clear_entity_type_cache(entity_type_id):
    """
    Remove the memoized serializations of the given entity type. Remove
    all the memoized searches by name, because the name is not known here.
    """
    cache.cache.delete_memoized(_get_entity_type_cached, str(entity_type_id))
    cache.cache.delete_memoized(get_entity_type_by_name)
    cache.cache.delete_memoized(get_entity_type_by_name_or_not_found)


def get_temporal_entity_type_by_name(name):
    """
    Return the entity type that has the given name. If it does not exist,
    create it.
    """
    return get_entity_type_by_name(name)


def is_edit(entity):
    """
    Return True if the entity type of the given entity dict is 'Edit'.
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
    Return the entity type that has the given ID as a dict. If it does not
    exist, raise EntityTypeNotFoundException.

    The ID becomes a string before the memoization, because the cache keys
    on the argument. Callers give a UUID from a row or a string. These two
    forms must not make two cache entries.
    """
    return _get_entity_type_cached(str(entity_type_id))


@cache.memoize_function(240)
def get_entity_type_by_name(name):
    """
    Return the entity type that has the given *name*. If it does not
    exist, create it.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        entity_type = EntityType.create(name=name)
    return entity_type.serialize()


@cache.memoize_function(240)
def get_entity_type_by_name_or_not_found(name):
    """
    Return the entity type that has the given *name*. If it does not
    exist, raise EntityTypeNotFoundException.
    """
    entity_type = EntityType.get_by(name=name)
    if entity_type is None:
        raise EntityTypeNotFoundException
    return entity_type.serialize()
