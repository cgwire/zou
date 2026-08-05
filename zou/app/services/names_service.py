import slugify

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.utils import cache

from zou.app.services import (
    entities_service,
    files_service,
    projects_service,
    tasks_service,
    shots_service,
    persons_service,
)


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
    entity = entities_service.get_entity(entity_id)
    episode_id = None
    if shots_service.is_shot(entity):
        sequence = entities_service.get_entity(entity["parent_id"])
        if sequence["parent_id"] is None:
            name = f"{sequence['name']} / {entity['name']}"
        else:
            episode = entities_service.get_entity(sequence["parent_id"])
            episode_id = episode["id"]
            name = f"{episode['name']} / {sequence['name']} / {entity['name']}"
    elif shots_service.is_episode(entity):
        name = entity["name"]
    elif shots_service.is_sequence(entity):
        name = entity["name"]
        if entity["parent_id"] is not None:
            episode = entities_service.get_entity(entity["parent_id"])
            episode_id = episode["id"]
            name = f"{episode['name']} / {entity['name']}"
    else:
        asset_type = entities_service.get_entity_type(entity["entity_type_id"])
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


def get_preview_file_name(preview_file_id):
    """
    Build unique and human readable file name for preview downloads. The
    convention followed is:
    [project_name]_[entity_name]_[task_type_name]_v[revivision].[extension].
    """
    organisation = persons_service.get_organisation()
    preview_file = files_service.get_preview_file(preview_file_id)
    task = tasks_service.get_task(preview_file["task_id"])
    task_type = tasks_service.get_task_type(task["task_type_id"])
    project = projects_service.get_project(task["project_id"])
    entity_name, _, _ = get_full_entity_name(task["entity_id"])

    if (
        organisation["use_original_file_name"]
        and preview_file.get("original_name", None) is not None
    ):
        name = preview_file["original_name"]
    else:
        name = (
            f"{project['name']}_{entity_name}_{task_type['name']}_v"
            f"{preview_file['revision']}"
        )
        name = slugify.slugify(name, separator="_")
    if (preview_file.get("position", 0) or 0) > 1:
        name = f"{name}-{preview_file['position']}"
    return f"{name}.{preview_file['extension']}"
