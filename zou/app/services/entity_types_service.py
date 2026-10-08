from sqlalchemy import func
from sqlalchemy.exc import StatementError

from zou.app import db
from zou.app.utils import events, cache, query as query_utils
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.services import base_service
from zou.app.exceptions import (
    AssetTypeNotFoundException,
    WrongParameterException,
    EntityTypeNotFoundException,
)


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


def is_episode(entity):
    """
    Returns True if given entity has 'Episode' as entity type
    """
    episode_type = get_episode_type()
    return str(entity["entity_type_id"]) == episode_type["id"]


def get_base_entity_type_name(entity_dict):
    """
    Return the entity type name of given entity, as the API names it:
    Shot, Sequence, Episode, Edit, Concept, ConceptFolder, or Asset for
    everything else.
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
    Drop the memoized asset type list, and the serialization of given
    asset type when one is named.
    """
    if asset_type_id is not None:
        cache.cache.delete_memoized(get_asset_type, asset_type_id)
        clear_entity_type_cache(asset_type_id)
    cache.cache.delete_memoized(get_all_asset_types)
    # get_asset_type carries the task types of the workflow, so editing it
    # must not keep serving the previous one for the whole TTL.
    cache.cache.delete_memoized(get_asset_type)


def get_temporal_type_ids():
    """
    Return the ids of the entity types that are not asset types: everything
    positioned in time (shot, sequence, episode, edit, scene, concept) and
    the folders the concepts are sorted in.
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


def get_asset_types(criterions=None):
    """
    Retrieve all asset types available. Only the no-criterion variant is
    memoized: criterion dicts vary per request and used to pollute the
    cache with entries that were never hit again.
    """
    if not criterions:
        return get_all_asset_types()
    criterions = dict(criterions)
    project_id = criterions.pop("project_id", None)
    query = EntityType.query.filter(build_entity_type_asset_type_filter())
    if project_id is not None:
        # An asset type belongs to no production: what a production holds
        # is assets of that type. The criterion is a membership test
        # rather than a column of the queried table, so it cannot go
        # through the generic criterion helper.
        query = query.filter(
            EntityType.id.in_(
                db.session.query(Entity.entity_type_id).filter(
                    Entity.project_id == project_id
                )
            )
        )
    # The queried table is EntityType. Handing the helper Entity built the
    # filters against the other table, which cross joined the two: the
    # project criterion then restricted nothing and the name criterion,
    # read off the assets rather than off their types, matched nothing.
    query = query_utils.apply_criterions_to_db_query(
        EntityType, query, criterions
    )
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


def serialize_asset_types(asset_type_ids):
    """
    Return the serialized asset types matching given ids, without querying
    when there is none.
    """
    result = []
    if len(asset_type_ids) > 0:
        result = EntityType.query.filter(
            EntityType.id.in_(list(asset_type_ids))
        ).all()
    return EntityType.serialize_list(result, obj_type="AssetType")


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


def find_asset_type_by_name(name):
    """
    Return the asset type matching given name as an active record, None
    when there is none.

    The match is case insensitive, to align with the asset type creation
    route which refuses a name already taken in another case. Resolving
    the temporal types first makes sure they exist before the lookup, so
    a name like Shot is recognised as one instead of read as an asset
    type.
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
    For a given name, get matching asset type. Create if it does not exist.
    """
    asset_type = find_asset_type_by_name(name)
    if asset_type is None:
        asset_type = EntityType.create(name=name)
        clear_asset_type_cache()
        events.emit("asset-type:new", {"asset_type_id": asset_type.id})

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


@cache.memoize_function(1200)
def get_concept_type():
    """
    Return the Concept entity type.
    """
    return get_temporal_entity_type_by_name("Concept")


def is_concept(entity):
    """
    Returns True if given entity has 'Concept' as entity type
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
    Returns True if given entity has 'ConceptFolder' as entity type
    """
    concept_folder_type = get_concept_folder_type()
    return str(entity["entity_type_id"]) == concept_folder_type["id"]


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
