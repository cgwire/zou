"""
Breakdown has two representations:

* Relation entries that link an asset and a shot. They can give a number
  of occurrences.
* One entry for each instance of an asset cast in a shot or a scene.

Warning: These two representations are not linked. Their data is not
synchronized.
"""

from flask import current_app
from slugify import slugify
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import DetachedInstanceError, StaleDataError

from zou.app.exceptions import (
    AssetInstanceNotFoundException,
    AssetNotFoundException,
    EntityLinkNotFoundException,
    WrongParameterException,
)
from zou.app.models.asset_instance import AssetInstance
from zou.app.models.entity import Entity, EntityLink
from zou.app.models.entity_type import EntityType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    base_service,
    entities_service,
    entity_types_service,
    projects_service,
    shots_service,
    tasks_service,
)
from zou.app.utils import events, fields


def get_casting(shot_id):
    """
    Return all assets and their number of occurrences in the given shot (or
    in the given asset, for set dressing).
    """
    casting = []
    links = (
        EntityLink.query.filter_by(entity_in_id=shot_id)
        .join(Entity, EntityLink.entity_out_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .filter(Entity.canceled != True)
        .add_columns(
            Entity.name,
            EntityType.name,
            Entity.preview_file_id,
            Entity.source_id,
            Entity.ready_for,
            Entity.is_shared,
            Entity.project_id,
        )
        .order_by(EntityType.name, Entity.name)
    )

    for (
        link,
        entity_name,
        entity_type_name,
        entity_preview_file_id,
        episode_id,
        entity_ready_for,
        entity_is_shared,
        entity_project_id,
    ) in links:
        casting.append(
            {
                "asset_id": fields.serialize_value(link.entity_out_id),
                "asset_name": entity_name,
                "asset_type_name": entity_type_name,
                "ready_for": fields.serialize_value(entity_ready_for),
                "episode_id": fields.serialize_value(episode_id),
                "preview_file_id": fields.serialize_value(
                    entity_preview_file_id
                ),
                "nb_occurences": link.nb_occurences,
                "label": link.label,
                "is_shared": entity_is_shared,
                "project_id": entity_project_id,
            }
        )
    return casting


def get_production_episodes_casting(project_id):
    """
    Return all assets and their number of occurrences in the episodes of the
    given project. Return a map: the keys are episode IDs and the values are
    the casting of each episode, ordered by asset type name and then by asset
    name.
    """
    castings = {}
    Episode = aliased(Entity, name="episode")
    links = (
        EntityLink.query.join(Episode, EntityLink.entity_in_id == Episode.id)
        .join(Entity, EntityLink.entity_out_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .filter(Episode.project_id == project_id)
        .filter(Entity.canceled != True)
        .add_columns(
            Entity.name,
            EntityType.name,
            Entity.preview_file_id,
            Entity.is_shared,
            Entity.project_id,
        )
        .order_by(
            EntityType.name,
            Entity.name,
        )
    )

    for (
        link,
        entity_name,
        entity_type_name,
        entity_preview_file_id,
        entity_is_shared,
        entity_project_id,
    ) in links:
        episode_id = str(link.entity_in_id)
        if episode_id not in castings:
            castings[episode_id] = []
        castings[episode_id].append(
            {
                "asset_id": fields.serialize_value(link.entity_out_id),
                "name": entity_name,
                "asset_name": entity_name,
                "asset_type_name": entity_type_name,
                "preview_file_id": fields.serialize_value(
                    entity_preview_file_id
                ),
                "nb_occurences": link.nb_occurences,
                "label": link.label,
                "is_shared": entity_is_shared,
                "project_id": entity_project_id,
            }
        )
    return castings


def get_sequence_casting(sequence_id, project_id=None, episode_id=None):
    """
    Return all assets and their number of occurrences in the shots of the
    given sequence. Return a map: the keys are shot IDs and the values are the
    casting of each shot.
    """
    castings = {}
    if episode_id == "main":
        return {}

    Shot = aliased(Entity, name="shot")
    Sequence = aliased(Entity, name="sequence")
    links = (
        EntityLink.query.join(Shot, EntityLink.entity_in_id == Shot.id)
        .join(Sequence, Shot.parent_id == Sequence.id)
        .join(Entity, EntityLink.entity_out_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .filter(Entity.canceled != True)
        .add_columns(
            Entity.name,
            EntityType.name,
            Entity.preview_file_id,
            Entity.is_shared,
            Entity.project_id,
            Sequence.name,
        )
    )

    if sequence_id is not None:
        links = links.filter(Shot.parent_id == sequence_id).order_by(
            Shot.name, EntityType.name, Entity.name
        )

    if project_id is not None:
        links = links.filter(Shot.project_id == project_id).order_by(
            Sequence.name, Shot.name, EntityType.name, Entity.name
        )

    if episode_id is not None:
        links = links.filter(Sequence.parent_id == episode_id).order_by(
            Sequence.name, Shot.name, EntityType.name, Entity.name
        )

    for (
        link,
        entity_name,
        entity_type_name,
        entity_preview_file_id,
        entity_is_shared,
        entity_project_id,
        sequence_name,
    ) in links:
        shot_id = str(link.entity_in_id)
        if shot_id not in castings:
            castings[shot_id] = []
        castings[shot_id].append(
            {
                "asset_id": fields.serialize_value(link.entity_out_id),
                "name": entity_name,
                "asset_name": entity_name,
                "asset_type_name": entity_type_name,
                "sequence_name": sequence_name,
                "preview_file_id": fields.serialize_value(
                    entity_preview_file_id
                ),
                "nb_occurences": link.nb_occurences,
                "label": link.label,
                "is_shared": entity_is_shared,
                "project_id": entity_project_id,
            }
        )
    return castings


def get_all_sequences_casting(project_id, episode_id=None):
    """
    Return all assets and their number of occurrences in the shots of the
    given project and episode. Return a map: the keys are shot IDs and the
    values are the casting of each shot.
    """
    return get_sequence_casting(
        None, project_id=project_id, episode_id=episode_id
    )


def get_asset_type_casting(project_id, asset_type_id):
    """
    Return all assets and their number of occurrences in the assets of the
    given asset type. Return a map: the keys are asset IDs and the values are
    the casting of each asset.
    """
    castings = {}
    Asset = aliased(Entity, name="asset")
    links = (
        EntityLink.query.join(Asset, EntityLink.entity_in_id == Asset.id)
        .join(Entity, EntityLink.entity_out_id == Entity.id)
        .join(EntityType, Entity.entity_type_id == EntityType.id)
        .filter(Asset.project_id == project_id)
        .filter(Asset.entity_type_id == asset_type_id)
        .filter(Entity.canceled != True)
        .add_columns(Entity.name, EntityType.name, Entity.preview_file_id)
        .order_by(EntityType.name, Entity.name)
    )

    for link, entity_name, entity_type_name, entity_preview_file_id in links:
        asset_id = str(link.entity_in_id)
        if asset_id not in castings:
            castings[asset_id] = []
        castings[asset_id].append(
            {
                "asset_id": fields.serialize_value(link.entity_out_id),
                "name": entity_name,
                "asset_name": entity_name,
                "asset_type_name": entity_type_name,
                "preview_file_id": fields.serialize_value(
                    entity_preview_file_id
                ),
                "nb_occurences": link.nb_occurences,
                "label": link.label,
            }
        )
    return castings


def get_shot_casting_export_rows(
    project_id, is_tv_show=False, episode_id=None
):
    """
    Return the casting rows of the shots of the given project, as tuples
    sorted by name. For a TV show, the rows start with the episode name and
    the given episode filters them.
    """
    results = []
    Shot = aliased(Entity, name="shot")
    Asset = aliased(Entity, name="asset")
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    AssetType = aliased(EntityType, name="asset_type")

    query = (
        EntityLink.query.join(Shot, EntityLink.entity_in_id == Shot.id)
        .join(Sequence, Shot.parent_id == Sequence.id)
        .join(Asset, EntityLink.entity_out_id == Asset.id)
        .join(AssetType, Asset.entity_type_id == AssetType.id)
        .filter(Shot.project_id == project_id)
    )
    if is_tv_show:
        query = query.join(Episode, Sequence.parent_id == Episode.id)
        if episode_id is not None:
            query = query.filter(Episode.id == episode_id)
        query = query.add_columns(
            Episode.name,
            Sequence.name,
            Shot.name,
            AssetType.name,
            Asset.name,
        ).order_by(
            Episode.name,
            Sequence.name,
            Shot.name,
            AssetType.name,
            Asset.name,
        )
        for (
            entity_link,
            episode_name,
            sequence_name,
            shot_name,
            asset_type_name,
            asset_name,
        ) in query.all():
            results.append(
                (
                    episode_name,
                    sequence_name,
                    "Shot",
                    shot_name,
                    asset_type_name,
                    asset_name,
                    entity_link.nb_occurences,
                    entity_link.label,
                )
            )
    else:
        query = query.add_columns(
            Sequence.name,
            Shot.name,
            AssetType.name,
            Asset.name,
        ).order_by(
            Sequence.name,
            Shot.name,
            AssetType.name,
            Asset.name,
        )

        for (
            entity_link,
            sequence_name,
            shot_name,
            asset_type_name,
            asset_name,
        ) in query.all():
            results.append(
                (
                    sequence_name,
                    "Shot",
                    shot_name,
                    asset_type_name,
                    asset_name,
                    entity_link.nb_occurences,
                    entity_link.label,
                )
            )

    return results


def get_asset_casting_export_rows(
    project_id, is_tv_show=False, episode_id=None
):
    """
    Return the casting rows of the assets of the given project, as tuples
    sorted by name. For a TV show, the rows start with the episode name, the
    given episode filters them and the main pack rows come at the end.
    """
    results = []
    ParentAsset = aliased(Entity, name="parent_asset")
    ParentAssetType = aliased(EntityType, name="parent_asset_type")
    Asset = aliased(Entity, name="asset")
    AssetType = aliased(EntityType, name="asset_type")
    Episode = aliased(Entity, name="episode")
    shot_type = entity_types_service.get_shot_type()

    query = (
        EntityLink.query.join(
            ParentAsset, EntityLink.entity_in_id == ParentAsset.id
        )
        .join(
            ParentAssetType,
            ParentAsset.entity_type_id == ParentAssetType.id,
        )
        .join(Asset, EntityLink.entity_out_id == Asset.id)
        .join(AssetType, Asset.entity_type_id == AssetType.id)
        .filter(ParentAsset.project_id == project_id)
        .filter(ParentAssetType.id != shot_type["id"])
    )
    if is_tv_show:
        query = query.join(Episode, ParentAsset.source_id == Episode.id)
        if episode_id is not None:
            query = query.filter(Episode.id == episode_id)
        query = query.add_columns(
            Episode.name,
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        ).order_by(
            Episode.name,
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        )
        for (
            entity_link,
            episode_name,
            parent_asset_type_name,
            parent_name,
            asset_type_name,
            asset_name,
        ) in query.all():
            results.append(
                (
                    episode_name,
                    "",
                    parent_asset_type_name,
                    parent_name,
                    asset_type_name,
                    asset_name,
                    entity_link.nb_occurences,
                    entity_link.label,
                )
            )
        results += get_main_pack_casting_export_rows(project_id)
    else:
        query = query.add_columns(
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        ).order_by(
            ParentAssetType.name,
            ParentAsset.name,
            AssetType.name,
            Asset.name,
        )
        for (
            entity_link,
            parent_asset_type_name,
            parent_name,
            asset_type_name,
            asset_name,
        ) in query.all():
            results.append(
                (
                    parent_asset_type_name,
                    "",
                    parent_name,
                    asset_type_name,
                    asset_name,
                    entity_link.nb_occurences,
                    entity_link.label,
                )
            )

    return results


def get_main_pack_casting_export_rows(project_id):
    """
    Return the casting rows of the assets of the main pack of the given
    project, as tuples sorted by name. The rows start with "MP".
    """
    results = []
    ParentAsset = aliased(Entity, name="parent_asset")
    ParentAssetType = aliased(EntityType, name="parent_asset_type")
    Asset = aliased(Entity, name="asset")
    AssetType = aliased(EntityType, name="asset_type")
    shot_type = entity_types_service.get_shot_type()
    episode_type = entity_types_service.get_episode_type()

    query = (
        EntityLink.query.join(
            ParentAsset, EntityLink.entity_in_id == ParentAsset.id
        )
        .join(
            ParentAssetType,
            ParentAsset.entity_type_id == ParentAssetType.id,
        )
        .join(Asset, EntityLink.entity_out_id == Asset.id)
        .join(AssetType, Asset.entity_type_id == AssetType.id)
        .filter(ParentAsset.project_id == project_id)
        .filter(ParentAsset.source_id == None)
        .filter(ParentAssetType.id != shot_type["id"])
        .filter(ParentAssetType.id != episode_type["id"])
    )
    query = query.add_columns(
        ParentAssetType.name,
        ParentAsset.name,
        AssetType.name,
        Asset.name,
    ).order_by(
        ParentAssetType.name,
        ParentAsset.name,
        AssetType.name,
        Asset.name,
    )
    for (
        entity_link,
        parent_asset_type_name,
        parent_name,
        asset_type_name,
        asset_name,
    ) in query.all():
        results.append(
            (
                "MP",
                "",
                parent_asset_type_name,
                parent_name,
                asset_type_name,
                asset_name,
                entity_link.nb_occurences,
                entity_link.label,
            )
        )
    return results


def get_episodes_casting_export_rows(project_id):
    """
    Return the casting rows of the episodes of the given project, as tuples
    sorted by name.
    """
    results = []
    ParentAsset = aliased(Entity, name="parent_asset")
    ParentAssetType = aliased(EntityType, name="parent_asset_type")
    Asset = aliased(Entity, name="asset")
    AssetType = aliased(EntityType, name="asset_type")
    episode_type = entity_types_service.get_episode_type()

    query = (
        EntityLink.query.join(
            ParentAsset, EntityLink.entity_in_id == ParentAsset.id
        )
        .join(
            ParentAssetType,
            ParentAsset.entity_type_id == ParentAssetType.id,
        )
        .join(Asset, EntityLink.entity_out_id == Asset.id)
        .join(AssetType, Asset.entity_type_id == AssetType.id)
        .filter(ParentAsset.project_id == project_id)
        .filter(ParentAsset.source_id == None)
        .filter(ParentAssetType.id == episode_type["id"])
    )
    query = query.add_columns(
        ParentAssetType.name,
        ParentAsset.name,
        AssetType.name,
        Asset.name,
    ).order_by(
        ParentAssetType.name,
        ParentAsset.name,
        AssetType.name,
        Asset.name,
    )
    for (
        entity_link,
        parent_asset_type_name,
        parent_name,
        asset_type_name,
        asset_name,
    ) in query.all():
        results.append(
            (
                "",
                parent_asset_type_name,
                parent_name,
                asset_type_name,
                asset_name,
                entity_link.nb_occurences,
                entity_link.label,
            )
        )
    return results


def update_casting(entity_id, casting):
    """
    Replace the casting of the given entity. The casting is a list of dicts
    made of `asset_id`, `nb_occurences` and an optional `label`. Skip the
    entries without `asset_id` or `nb_occurences`. On an episode, the removed
    assets also leave the casting of its shots. Return the given casting.
    """

    entity = entities_service.get_entity_raw(entity_id)
    entity_dict = entity.serialize(relations=True)

    # Keep a copy of the casting before the change, thus the emitted event
    # can carry an explicit added/removed diff. Else, listeners must keep
    # their own client-side copy to know what changed.
    previous_asset_ids = {
        str(asset_id) for asset_id in entity_dict.get("entities_out") or []
    }
    new_asset_ids = {
        str(cast["asset_id"])
        for cast in casting
        if "asset_id" in cast and "nb_occurences" in cast
    }
    added_asset_ids = sorted(new_asset_ids - previous_asset_ids)
    removed_asset_ids = sorted(previous_asset_ids - new_asset_ids)

    if entity_types_service.is_episode(entity_dict):
        assets = _extract_removal(entity_dict, casting)
        for asset_id in assets:
            _remove_asset_from_episode_shots(asset_id, entity_id)
    entity.update({"entities_out": [], "nb_entities_out": 0})
    for cast in casting:
        if "asset_id" in cast and "nb_occurences" in cast:
            create_casting_link(
                entity.id,
                cast["asset_id"],
                nb_occurences=cast["nb_occurences"],
                label=cast.get("label", ""),
            )
            if entity_types_service.is_episode(entity_dict):
                events.emit(
                    "asset:update",
                    {"asset_id": cast["asset_id"]},
                    project_id=str(entity.project_id),
                )

    _announce_casting_change(entity, added_asset_ids, removed_asset_ids)
    return casting


def _announce_casting_change(entity, added_asset_ids, removed_asset_ids):
    """
    Refresh the data that depends on the casting of the given entity after
    its links changed:
    - its link count,
    - the cached serializations,
    - the shot stats,
    - the episode links that come from the shots,
    - the listeners, through a casting-update event that carries the diff.
    """
    entity_id = str(entity.id)
    entity.update({"nb_entities_out": _count_live_links(entity.id)})
    _clear_casting_cache(entity_id)
    entity_dict = entity.serialize()
    casting_diff = {
        "nb_entities_out": entity.nb_entities_out,
        "added_asset_ids": added_asset_ids,
        "removed_asset_ids": removed_asset_ids,
    }
    if entity_types_service.is_shot(entity_dict):
        refresh_shot_casting_stats(entity_dict)
        events.emit(
            "shot:casting-update",
            {"shot_id": entity_id, **casting_diff},
            project_id=str(entity.project_id),
        )
        if removed_asset_ids:
            episode_id = _get_episode_id_for_shot(entity_dict)
            if episode_id is not None:
                for asset_id in removed_asset_ids:
                    _detach_asset_from_episode_if_unused(asset_id, episode_id)
    elif entity_types_service.is_episode(entity_dict):
        events.emit(
            "episode:casting-update",
            {"episode_id": entity_id, **casting_diff},
            project_id=str(entity.project_id),
        )
    else:
        events.emit(
            "asset:casting-update",
            {"asset_id": entity_id, **casting_diff},
            project_id=str(entity.project_id),
        )


def cast_asset(entity_id, asset_id, nb_occurences=None, label=None):
    """
    Cast the given asset in the given entity. Do not change the other assets
    of its casting: a caller that has an old view of the casting cannot erase
    them. If a count or a label is None, keep the current value (one
    occurrence and no label on a new link).
    """
    entity = entities_service.get_entity_raw(entity_id)
    link = get_entity_link_raw(entity_id, asset_id)
    if nb_occurences is None:
        nb_occurences = link.nb_occurences if link else 1
    if label is None:
        label = link.label if link else ""
    create_casting_link(entity.id, asset_id, nb_occurences, label)
    # The asset list of an episode comes from its casting: the asset is
    # now in the episode, and only asset:update makes the clients load it
    # again (same as update_casting on an episode).
    if entity_types_service.is_episode(entity.serialize()):
        events.emit(
            "asset:update",
            {"asset_id": str(asset_id)},
            project_id=str(entity.project_id),
        )
    added_asset_ids = [] if link else [str(asset_id)]
    _announce_casting_change(entity, added_asset_ids, [])
    return get_casting(entity_id)


def uncast_asset(entity_id, asset_id, cascade_to_shots=True):
    """
    Remove the given asset from the casting of the given entity. Do not
    change the other assets. If the asset was not cast, do nothing. On an
    episode, the asset also leaves the casting of its shots, unless
    cascade_to_shots is False.
    """
    link = get_entity_link_raw(entity_id, asset_id)
    if link is None:
        return get_casting(entity_id)
    entity = entities_service.get_entity_raw(entity_id)
    if cascade_to_shots and entity_types_service.is_episode(
        entity.serialize()
    ):
        _remove_asset_from_episode_shots(asset_id, entity_id)
    link.delete()
    _announce_casting_change(entity, [], [str(asset_id)])
    return get_casting(entity_id)


def _clear_casting_cache(entity_id):
    """
    Remove the memoized serializations of an entity whose casting changed.
    They carry nb_entities_out. create_casting_link reads the entity before
    it writes the link, thus the count is cached before the write.
    """
    entity_id = str(entity_id)
    if entity_types_service.is_shot(entities_service.get_entity(entity_id)):
        shots_service.clear_shot_cache(entity_id)
    else:
        entities_service.clear_entity_cache(entity_id)


def create_casting_link(entity_in_id, asset_id, nb_occurences=1, label=""):
    """
    Create or update the link between the given entity and the given asset.
    A new link on a shot also casts the asset in its episode. Log the
    duplicate link errors that concurrent requests cause, do not raise them.
    Return the link, or None if a concurrent request created it first.
    """
    try:
        link = EntityLink.get_by(
            entity_in_id=entity_in_id, entity_out_id=asset_id
        )
        entity = entities_service.get_entity(entity_in_id)
        project_id = str(entity["project_id"])
        if link is None:
            _create_episode_casting_link(entity, asset_id, 1, label)
            link = EntityLink.create(
                entity_in_id=entity_in_id,
                entity_out_id=asset_id,
                nb_occurences=nb_occurences,
                label=label,
            )
            events.emit(
                "entity-link:new",
                {
                    "entity_link_id": link.id,
                    "entity_in_id": link.entity_in_id,
                    "entity_out_id": link.entity_out_id,
                    "nb_occurences": nb_occurences,
                },
                project_id=project_id,
            )
        else:
            link.update({"nb_occurences": nb_occurences, "label": label})
            events.emit(
                "entity-link:update",
                {"entity_link_id": link.id, "nb_occurences": nb_occurences},
                project_id=project_id,
            )
    except IntegrityError:
        current_app.logger.warning(
            "Attempt to create duplicated entity links (link already created) via create_casting_link (raised by sqlalchemy.exc.IntegrityError)"
        )
    except StaleDataError:
        current_app.logger.warning(
            "Attempt to create duplicated entity links (concurrent modification) via zou.app.services.breakdown_service.create_casting_link (raised by sqlalchemy.orm.exc.StaleDataError)"
        )
    except DetachedInstanceError:
        current_app.logger.warning(
            "Attempt to create duplicated entity links (attempt to access unloaded attributes on a mapped instance that is detached) via zou.app.services.breakdown_service.create_casting_link (raised by sqlalchemy.orm.exc.DetachedInstanceError)"
        )
    return link


def import_casting_link(entity, asset_id, nb_occurences, label):
    """
    Create the link between the given entity active record and the given
    asset, and add one to the link count of the entity. If the link exists,
    update its occurences and label, without event.
    """
    entity_id = str(entity.id)
    link = get_entity_link_raw(entity_id, asset_id)
    if link is None:
        create_casting_link(entity_id, asset_id, nb_occurences, label)
        entity.update({"nb_entities_out": entity.nb_entities_out + 1})
        entities_service.clear_entity_cache(entity_id)
    else:
        link.update({"nb_occurences": nb_occurences, "label": label})


def _extract_removal(entity, casting):
    """
    Return the assets removed from the casting of an entity: the assets that
    it was linked to and that the new casting does not name.
    """
    assets = []
    asset_map = {}
    for cast in casting:
        asset_map[cast["asset_id"]] = True
    for entity_id in entity["entities_out"]:
        if entity_id not in asset_map:
            assets.append(entity_id)
    return assets


def _remove_asset_from_episode_shots(asset_id, episode_id):
    """
    Remove an asset from the casting of each shot of the given episode.
    """
    shots = shots_service.get_shots_for_episode(episode_id)
    shot_ids = [shot["id"] for shot in shots]
    links = EntityLink.query.filter(
        EntityLink.entity_in_id.in_(shot_ids)
    ).filter(EntityLink.entity_out_id == asset_id)
    for link in links:
        shot = shots_service.get_shot_raw(str(link.entity_in_id))
        link.delete()
        shots_service.clear_shot_cache(str(shot.id))
        # This counts the links, thus it runs after the link removal.
        refresh_shot_casting_stats(shot.serialize())
        events.emit(
            "shot:casting-update",
            {
                "shot_id": str(shot.id),
                "nb_entities_out": shot.nb_entities_out,
                "added_asset_ids": [],
                "removed_asset_ids": [str(asset_id)],
            },
            project_id=str(shot.project_id),
        )
    return shots


def _get_episode_id_for_shot(shot):
    """
    Return the ID of the episode of the given shot. Return None if its
    sequence has no parent episode or if the shot has no sequence.
    """
    if shot["parent_id"] is None:
        return None
    sequence = shots_service.get_sequence(str(shot["parent_id"]))
    return sequence["parent_id"]


def _detach_asset_from_episode_if_unused(asset_id, episode_id):
    """
    Remove the asset from the parent episode after its removal from the
    casting of a shot, unless the asset is still cast in another shot of that
    episode. This is the opposite of `_create_episode_casting_link`: a cast in
    a shot also casts the asset in the parent episode.
    """
    shots = shots_service.get_shots_for_episode(episode_id)
    shot_ids = [shot["id"] for shot in shots]
    is_still_casted_in_a_shot = (
        len(shot_ids) > 0
        and EntityLink.query.filter(EntityLink.entity_in_id.in_(shot_ids))
        .filter(EntityLink.entity_out_id == asset_id)
        .first()
        is not None
    )
    if is_still_casted_in_a_shot:
        return

    link = EntityLink.get_by(entity_in_id=episode_id, entity_out_id=asset_id)
    # A link that the manager set from the episode breakdown has no flag:
    # it is a separate decision, not a copy of the shots.
    if link is None or not (link.data or {}).get("auto"):
        return

    episode = entities_service.get_entity_raw(episode_id)
    link.delete()
    episode.update({"nb_entities_out": max(episode.nb_entities_out - 1, 0)})
    entities_service.clear_entity_cache(str(episode_id))
    events.emit(
        "episode:casting-update",
        {
            "episode_id": str(episode_id),
            "nb_entities_out": episode.nb_entities_out,
            "added_asset_ids": [],
            "removed_asset_ids": [str(asset_id)],
        },
        project_id=str(episode.project_id),
    )
    # Emit the same asset:update event as when the link was created
    # automatically in `_create_episode_casting_link`. Thus listeners
    # refresh the asset the same way on both sides of the auto-casting link.
    events.emit(
        "asset:update",
        {"asset_id": str(asset_id)},
        project_id=str(episode.project_id),
    )


def _create_episode_casting_link(entity, asset_id, nb_occurences=1, label=""):
    """
    If an asset is cast in a shot, cast the asset automatically in the
    episode, with a link flagged as auto.
    """
    # A shot created before its sequences exist has no parent. Then there
    # is no episode to cast the asset in.
    if (
        entity_types_service.is_shot(entity)
        and entity["parent_id"] is not None
    ):
        sequence = shots_service.get_sequence(entity["parent_id"])
        if sequence["parent_id"] is not None:
            link = EntityLink.get_by(
                entity_in_id=sequence["parent_id"], entity_out_id=asset_id
            )
            if link is None:
                link = EntityLink.create(
                    entity_in_id=sequence["parent_id"],
                    entity_out_id=asset_id,
                    nb_occurences=nb_occurences,
                    label=label,
                    data={"auto": True},
                )
                # The breakdown of the episode comes from this count, and
                # the removal path below decreases it. Without this, an
                # episode cast through its shots showed no assets.
                episode = entities_service.get_entity_raw(
                    sequence["parent_id"]
                )
                episode.update(
                    {"nb_entities_out": (episode.nb_entities_out or 0) + 1}
                )
                entities_service.clear_entity_cache(sequence["parent_id"])
                events.emit(
                    "asset:update",
                    {"asset_id": asset_id},
                    project_id=entity["project_id"],
                )
    return entity


def get_cast_in(asset_id):
    """
    Return the list of shots, then of assets, in which an asset is cast.
    """
    cast_in = []
    Sequence = aliased(Entity, name="sequence")
    Episode = aliased(Entity, name="episode")
    links = (
        EntityLink.query.filter_by(entity_out_id=asset_id)
        .filter(Entity.canceled != True)
        .join(Entity, EntityLink.entity_in_id == Entity.id)
        .join(Sequence, Entity.parent_id == Sequence.id)
        .outerjoin(Episode, Sequence.parent_id == Episode.id)
        .add_columns(
            Entity.name,
            Sequence.name,
            Episode.id,
            Episode.name,
            Entity.preview_file_id,
        )
        .order_by(Episode.name, Sequence.name, Entity.name)
    )

    for (
        link,
        entity_name,
        sequence_name,
        episode_id,
        episode_name,
        entity_preview_file_id,
    ) in links:
        shot = {
            "shot_id": fields.serialize_value(link.entity_in_id),
            "shot_name": entity_name,
            "sequence_name": sequence_name,
            "episode_id": str(episode_id),
            "episode_name": episode_name,
            "preview_file_id": fields.serialize_value(entity_preview_file_id),
            "nb_occurences": link.nb_occurences,
        }
        cast_in.append(shot)

    links = (
        EntityLink.query.filter_by(entity_out_id=asset_id)
        .filter(Entity.canceled != True)
        .filter(entity_types_service.build_entity_type_asset_type_filter())
        .join(Entity, EntityLink.entity_in_id == Entity.id)
        .join(EntityType, EntityType.id == Entity.entity_type_id)
        .add_columns(Entity.name, EntityType.name, Entity.preview_file_id)
        .order_by(EntityType.name, Entity.name)
    )

    for link, entity_name, entity_type_name, entity_preview_file_id in links:
        shot = {
            "asset_id": fields.serialize_value(link.entity_in_id),
            "asset_name": entity_name,
            "asset_type_name": entity_type_name,
            "preview_file_id": fields.serialize_value(entity_preview_file_id),
            "nb_occurences": link.nb_occurences,
        }
        cast_in.append(shot)

    return cast_in


def _group_serialized_instances(keyed_instances):
    """
    Group the serialized asset instances by key, from the given (key,
    instance) pairs.
    """
    result = {}
    for key, asset_instance in keyed_instances:
        result.setdefault(key, []).append(asset_instance.serialize())
    return result


def _get_instances_of_asset(asset_id):
    """
    Return all asset instances of the given asset, ordered by number.
    """
    return (
        AssetInstance.query.filter(AssetInstance.asset_id == asset_id)
        .order_by(AssetInstance.asset_id, AssetInstance.number)
        .all()
    )


def get_asset_instances_for_scene(scene_id, asset_type_id=None):
    """
    Return all asset instances for the given scene.

    Asset instances are a different representation of the casting of a shot.
    They help to track precisely the output files that the build of a shot
    generates.
    """
    query = AssetInstance.query.filter(
        AssetInstance.scene_id == scene_id
    ).order_by(AssetInstance.asset_id, AssetInstance.number)

    if asset_type_id is not None:
        query = query.join(Entity, AssetInstance.asset_id == Entity.id).filter(
            Entity.entity_type_id == asset_type_id
        )

    return _group_serialized_instances(
        (str(asset_instance.asset_id), asset_instance)
        for asset_instance in query.all()
    )


def get_asset_instances_for_shot(shot_id):
    """
    Return the asset instances cast in the given shot.
    """
    shot = shots_service.get_shot_raw(shot_id)
    return _group_serialized_instances(
        (str(asset_instance.asset_id), asset_instance)
        for asset_instance in shot.instance_casting
    )


def get_shot_asset_instances_for_asset(asset_id):
    """
    Return the asset instances cast in a shot for the given asset.
    """
    return _group_serialized_instances(
        (str(shot.id), asset_instance)
        for asset_instance in _get_instances_of_asset(asset_id)
        for shot in asset_instance.shots
    )


def get_scene_asset_instances_for_asset(asset_id):
    """
    Return all asset instances of an asset cast in layout scenes.
    """
    return _group_serialized_instances(
        (str(asset_instance.scene_id), asset_instance)
        for asset_instance in _get_instances_of_asset(asset_id)
    )


def get_camera_instances_for_scene(scene_id):
    """
    Return all instances of type Camera for the given layout scene.
    """
    camera_entity_type = entity_types_service.get_or_create_asset_type(
        "Camera"
    )
    return get_asset_instances_for_scene(scene_id, camera_entity_type["id"])


def add_asset_instance_to_scene(scene_id, asset_id, description=""):
    """
    Create an asset instance for the given asset and scene.
    """
    instance = (
        AssetInstance.query.filter(AssetInstance.scene_id == scene_id)
        .filter(AssetInstance.asset_id == asset_id)
        .order_by(desc(AssetInstance.number))
        .first()
    )

    number = 1 if instance is None else instance.number + 1
    name = build_asset_instance_name(asset_id, number)

    asset_instance = AssetInstance.create(
        asset_id=asset_id,
        scene_id=scene_id,
        number=number,
        name=name,
        description=description,
    ).serialize()

    events.emit(
        "asset_instance:new",
        {
            "scene_id": scene_id,
            "asset_id": asset_id,
            "asset_instance_id": asset_instance["id"],
        },
    )
    return asset_instance


def add_asset_instance_to_shot(shot_id, asset_instance_id):
    """
    Add the asset instance to the instance casting of the given shot. If
    the scene or the target asset of the instance is in another project,
    raise a WrongParameterException.
    """
    shot = shots_service.get_shot_raw(shot_id)
    asset_instance = get_asset_instance_raw(asset_instance_id)
    for parent_id in (asset_instance.scene_id, asset_instance.target_asset_id):
        if (
            parent_id is not None
            and Entity.get(parent_id).project_id != shot.project_id
        ):
            raise WrongParameterException(
                f"Asset instance {asset_instance_id} is not in the project "
                "of the shot."
            )
    shot.instance_casting.append(asset_instance)
    shot.save()

    events.emit(
        "asset_instance:add-to-shot",
        {"shot_id": shot_id, "asset_instance_id": asset_instance_id},
    )
    return shot.serialize()


def remove_asset_instance_for_shot(shot_id, asset_instance_id):
    """
    Remove the asset instance from the instance casting of the given shot.
    If the instance is not cast in the shot, raise a
    WrongParameterException.
    """
    shot = shots_service.get_shot_raw(shot_id)
    asset_instance = get_asset_instance_raw(asset_instance_id)
    if asset_instance not in shot.instance_casting:
        raise WrongParameterException(
            f"Asset instance {asset_instance_id} is not cast in the shot."
        )
    shot.instance_casting.remove(asset_instance)
    shot.save()
    events.emit(
        "asset_instance:remove-from-shot",
        {"shot_id": shot_id, "asset_instance_id": asset_instance_id},
    )
    return shot.serialize()


def build_asset_instance_name(asset_id, number):
    """
    Return a normalized asset instance name. It is used to build default
    instance names.
    """
    asset = base_service.get_instance(Entity, asset_id, AssetNotFoundException)
    asset_name = slugify(asset.name, separator="_", lowercase=False)
    number = str(number).zfill(4)
    return f"{asset_name}_{number}"


def get_asset_instances_for_asset(asset_id, asset_type_id=None):
    """
    Return all asset instances inside the given asset.

    Asset instances of an asset are used for environments (instances of
    props) or for props (instances of sub props).
    """
    query = AssetInstance.query.filter(
        AssetInstance.target_asset_id == asset_id
    ).order_by(AssetInstance.asset_id, AssetInstance.number)

    if asset_type_id is not None:
        query = query.join(Entity, AssetInstance.asset_id == Entity.id).filter(
            Entity.entity_type_id == asset_type_id
        )

    return _group_serialized_instances(
        (str(asset_instance.asset_id), asset_instance)
        for asset_instance in query.all()
    )


def add_asset_instance_to_asset(
    asset_id, asset_to_instantiate_id, description=""
):
    """
    Create an instance of the asset to instantiate inside the given asset.
    """
    instance = (
        AssetInstance.query.filter(AssetInstance.target_asset_id == asset_id)
        .filter(AssetInstance.asset_id == asset_to_instantiate_id)
        .order_by(desc(AssetInstance.number))
        .first()
    )

    number = 1 if instance is None else instance.number + 1
    name = build_asset_instance_name(asset_to_instantiate_id, number)

    asset_instance = AssetInstance.create(
        asset_id=asset_to_instantiate_id,
        target_asset_id=asset_id,
        number=number,
        name=name,
        description=description,
    ).serialize()

    events.emit(
        "asset_instance:new",
        {
            "asset_id": asset_id,
            "asset_instantiated": asset_to_instantiate_id,
            "asset_instance_id": asset_instance["id"],
        },
    )
    return asset_instance


def get_entity_casting(entity_id):
    """
    Return the entities related to the entity as external entities.
    """
    entity = entities_service.get_entity_raw(entity_id)
    return Entity.serialize_list(entity.entities_out, obj_type="Asset")


def get_entity_link_raw(entity_in_id, entity_out_id):
    """
    Return the link that matches the given entities.
    """
    link = EntityLink.get_by(
        entity_in_id=entity_in_id, entity_out_id=entity_out_id
    )
    return link


def get_entity_link_between(entity_in_id, entity_out_id):
    """
    Return the link that matches the given entities.
    """
    link = get_entity_link_raw(entity_in_id, entity_out_id)
    if link:
        return link.serialize()
    else:
        return None


def refresh_casting_stats(asset):
    """
    For each shot that includes the given asset, compute for each related
    task the number of available assets. Save the result on the task level.
    """

    cast_in = get_cast_in(asset["id"])
    shots = [entity for entity in cast_in if "shot_id" in entity]
    priority_map = _get_task_type_priority_map(asset["project_id"])
    for shot in shots:
        refresh_shot_casting_stats(
            {"id": shot["shot_id"], "project_id": asset["project_id"]},
            priority_map,
        )
    return asset


def refresh_shot_casting_stats(shot, priority_map=None):
    """
    For all tasks related to the given shot, compute the number of available
    assets for each task. Save the result on the task level. Also sync the
    nb_entities_out of the shot with its live links again.
    """
    if priority_map is None:
        priority_map = _get_task_type_priority_map(shot["project_id"])
    # The shots page divides the ready count by this counter. The casting
    # page lists the live links. The archive of an asset keeps its links,
    # the deletion of an asset removes them, and neither path changed the
    # counter.
    shot_raw = Entity.get(shot["id"])
    nb_live = _count_live_links(shot["id"])
    if shot_raw.nb_entities_out != nb_live:
        shot_raw.update({"nb_entities_out": nb_live})
        shots_service.clear_shot_cache(shot["id"])
        events.emit(
            "shot:casting-update",
            {
                "shot_id": shot["id"],
                "nb_entities_out": nb_live,
                "added_asset_ids": [],
                "removed_asset_ids": [],
            },
            project_id=shot["project_id"],
        )
    casting = get_entity_casting(shot["id"])
    tasks = Task.get_all_by(entity_id=shot["id"])
    for task in tasks:
        nb_ready = 0
        for asset in casting:
            if _is_asset_ready(asset, task, priority_map):
                nb_ready += 1
        task.update({"nb_assets_ready": nb_ready})
        tasks_service.clear_task_cache(str(task.id))
        events.emit(
            "task:update-casting-stats",
            {"task_id": str(task.id), "nb_assets_ready": nb_ready},
            persist=False,
            project_id=shot["project_id"],
        )


def refresh_all_shot_casting_stats():
    """
    For all shots in all open projects, compute the number of available
    assets. Save the result on the task level.
    """
    for project in projects_service.open_projects():
        priority_map = _get_task_type_priority_map(project["id"])
        for shot in shots_service.get_shots_for_project(project["id"]):
            refresh_shot_casting_stats(shot, priority_map)


def _count_live_links(entity_id):
    """
    Count the assets that are cast in the given entity and that are not
    canceled. get_casting lists the same assets.
    """
    return (
        EntityLink.query.filter_by(entity_in_id=entity_id)
        .join(Entity, EntityLink.entity_out_id == Entity.id)
        .filter(Entity.canceled != True)
        .count()
    )


def _get_task_type_priority_map(project_id):
    """
    Map each shot task type of a project to its priority. The priority gives
    the order of the pipeline steps.
    """
    task_types = (
        ProjectTaskTypeLink.query.join(TaskType)
        .filter(ProjectTaskTypeLink.project_id == project_id)
        .filter(TaskType.for_entity == "Shot")
        .all()
    )
    priority_map = {
        str(task_type_link.task_type_id): task_type_link.priority
        for task_type_link in task_types
    }
    return priority_map


def _is_asset_ready(asset, task, priority_map):
    """
    Return True if an asset is ready for the given task. A shared asset from
    another project is always ready. Else, its ready_for step must come at
    or after the step of the task in the pipeline order.
    """
    is_ready = False
    if not asset.get("canceled", False):
        if asset["is_shared"] and asset["project_id"] != str(task.project_id):
            is_ready = True
        elif "ready_for" in asset and asset["ready_for"] is not None:
            priority_ready = priority_map.get(asset["ready_for"], -1) or -1
            priority_task = priority_map.get(str(task.task_type_id), 0) or 0
            is_ready = priority_task <= priority_ready
    return is_ready


def remove_entity_link(link_id):
    """
    Delete the entity link that matches the given ID and return it. The
    deletion goes through the breakdown uncast operation, which refreshes
    the link counter, the casting caches and stats, and the episode link that
    comes from the shots. The removal of one link does not change the shots
    of an episode.
    """

    link = EntityLink.get_by(id=link_id)
    if link is None:
        raise EntityLinkNotFoundException
    serialized_link = link.serialize()
    uncast_asset(link.entity_in_id, link.entity_out_id, cascade_to_shots=False)
    return serialized_link


def get_asset_instance_raw(asset_instance_id):
    """
    Return the given asset instance as an active record.
    """
    return base_service.get_instance(
        AssetInstance, asset_instance_id, AssetInstanceNotFoundException
    )


def get_asset_instance(asset_instance_id):
    """
    Return the given asset instance as a dict.
    """
    return get_asset_instance_raw(asset_instance_id).serialize()
