import slugify

from zou.app.models.entity import Entity
from zou.app.utils import cache

from zou.app.services import (
    entities_service,
    files_service,
    projects_service,
    tasks_service,
    shots_service,
    persons_service,
)


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
            name = "%s / %s" % (sequence["name"], entity["name"])
        else:
            episode = entities_service.get_entity(sequence["parent_id"])
            episode_id = episode["id"]
            name = "%s / %s / %s" % (
                episode["name"],
                sequence["name"],
                entity["name"],
            )
    elif shots_service.is_episode(entity):
        name = entity["name"]
    elif shots_service.is_sequence(entity):
        name = entity["name"]
        if entity["parent_id"] is None:
            name = entity["name"]
        else:
            episode = entities_service.get_entity(entity["parent_id"])
            episode_id = episode["id"]
            name = "%s / %s" % (
                episode["name"],
                entity["name"],
            )
    else:
        asset_type = entities_service.get_entity_type(entity["entity_type_id"])
        episode_id = entity["source_id"]
        name = "%s / %s" % (asset_type["name"], entity["name"])
    return (name, episode_id, entity["preview_file_id"])


def get_full_entity_names(entity_ids):
    """
    Batch version of get_full_entity_name. Takes a list of entity IDs
    and returns a dict mapping entity_id -> (name, episode_id,
    preview_file_id). Uses 2-3 queries instead of N.
    """
    if not entity_ids:
        return {}

    unique_ids = list(set(entity_ids))

    # Fetch all entities in one query
    entities_raw = Entity.query.filter(Entity.id.in_(unique_ids)).all()
    entities_map = {str(e.id): e.serialize() for e in entities_raw}

    # Collect parent IDs we need to fetch
    parent_ids = set()
    for entity in entities_map.values():
        if entity["parent_id"] is not None:
            parent_ids.add(entity["parent_id"])

    # Fetch parents in one query
    parents_map = {}
    if parent_ids:
        # Remove IDs we already have
        missing_parent_ids = parent_ids - set(entities_map.keys())
        if missing_parent_ids:
            parents_raw = Entity.query.filter(
                Entity.id.in_(list(missing_parent_ids))
            ).all()
            for e in parents_raw:
                parents_map[str(e.id)] = e.serialize()
        # Also include entities that are parents of other entities
        for pid in parent_ids:
            if str(pid) in entities_map:
                parents_map[str(pid)] = entities_map[str(pid)]

    # Collect grandparent IDs (episode of a sequence)
    grandparent_ids = set()
    for parent in parents_map.values():
        if parent["parent_id"] is not None:
            grandparent_ids.add(parent["parent_id"])

    # Fetch grandparents in one query
    grandparents_map = {}
    if grandparent_ids:
        missing = (
            grandparent_ids
            - set(entities_map.keys())
            - set(parents_map.keys())
        )
        if missing:
            gp_raw = Entity.query.filter(Entity.id.in_(list(missing))).all()
            for e in gp_raw:
                grandparents_map[str(e.id)] = e.serialize()
        for gid in grandparent_ids:
            sid = str(gid)
            if sid in entities_map:
                grandparents_map[sid] = entities_map[sid]
            elif sid in parents_map:
                grandparents_map[sid] = parents_map[sid]

    # All entities lookup
    all_entities = {}
    all_entities.update(grandparents_map)
    all_entities.update(parents_map)
    all_entities.update(entities_map)

    # Get type IDs for classification
    shot_type = shots_service.get_shot_type()
    episode_type = shots_service.get_episode_type()
    sequence_type = shots_service.get_sequence_type()

    # Collect entity_type_ids for asset types
    asset_type_ids = set()
    for entity in entities_map.values():
        etype = str(entity["entity_type_id"])
        if etype not in (
            shot_type["id"],
            episode_type["id"],
            sequence_type["id"],
        ):
            asset_type_ids.add(entity["entity_type_id"])

    # Batch fetch asset types
    asset_types_map = {}
    if asset_type_ids:
        from zou.app.models.entity_type import EntityType

        types_raw = EntityType.query.filter(
            EntityType.id.in_(list(asset_type_ids))
        ).all()
        for t in types_raw:
            asset_types_map[str(t.id)] = t.serialize()

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
                name = "%s / %s" % (parent["name"], entity["name"])
            else:
                grandparent = all_entities.get(str(parent["parent_id"]))
                if grandparent:
                    episode_id = grandparent["id"]
                    name = "%s / %s / %s" % (
                        grandparent["name"],
                        parent["name"],
                        entity["name"],
                    )
                else:
                    name = "%s / %s" % (
                        parent["name"],
                        entity["name"],
                    )
        elif etype == episode_type["id"]:
            name = entity["name"]
        elif etype == sequence_type["id"]:
            if entity["parent_id"] is None:
                name = entity["name"]
            else:
                parent = all_entities.get(str(entity["parent_id"]))
                if parent:
                    episode_id = parent["id"]
                    name = "%s / %s" % (
                        parent["name"],
                        entity["name"],
                    )
                else:
                    name = entity["name"]
        else:
            asset_type = asset_types_map.get(str(entity["entity_type_id"]))
            episode_id = entity["source_id"]
            if asset_type:
                name = "%s / %s" % (
                    asset_type["name"],
                    entity["name"],
                )
            else:
                name = entity["name"]

        result[str_eid] = (
            name,
            episode_id,
            entity["preview_file_id"],
        )

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
        name = "%s_%s_%s_v%s" % (
            project["name"],
            entity_name,
            task_type["name"],
            preview_file["revision"],
        )
        name = slugify.slugify(name, separator="_")
    if (preview_file.get("position", 0) or 0) > 1:
        name = "%s-%s" % (name, preview_file["position"])
    return "%s.%s" % (name, preview_file["extension"])
