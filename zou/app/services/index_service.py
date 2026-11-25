import logging

from flask import current_app

from zou.app.indexer import indexing
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.services import (
    entity_types_service,
    metadata_descriptors_service,
    projects_service,
)

logger = logging.getLogger(__name__)


def get_index(index_name):
    """
    Return the Meilisearch index that has the given name from the indexer.
    All operations need it.
    """
    return indexing.get_index(index_name)


def get_asset_index():
    """
    Return the Meilisearch index that holds the assets.
    """
    return get_index("assets")


def get_person_index():
    """
    Return the Meilisearch index that holds the persons.
    """
    return get_index("persons")


def get_shot_index():
    """
    Return the Meilisearch index that holds the shots.
    """
    return get_index("shots")


def _index_entry(get_entry_index, prepare_entry, entry):
    """
    Build the document for the given entry and push it to its index. If the
    indexer is absent or cannot be reached, ignore the error: indexation
    must never break the request that started it.
    """
    try:
        index = get_entry_index()
        document = prepare_entry(entry)
        indexing.index_document(index, document)
        return document
    except indexing.IndexerNotInitializedError:
        pass
    except Exception:
        current_app.logger.error(
            "Indexer is not reachable, indexation failed."
        )
    return {}


def _index_entries(get_entry_index, prepare_entry, entry_ids):
    """
    Build the documents of the entities that match the given IDs and push
    them to their index. Make one call for each chunk and do not wait for
    Meilisearch: a bulk import must not wait on the indexer for each row. A
    new document replaces the document with the same ID, thus an updated
    entity does not need a removal first. If the indexer is absent or cannot
    be reached, ignore the error, as for a single entry.
    """
    documents = []
    if not entry_ids:
        return documents
    try:
        index = get_entry_index()
        for start in range(0, len(entry_ids), 3000):
            entries = Entity.query.filter(
                Entity.id.in_(entry_ids[start : start + 3000])
            ).all()
            chunk = [prepare_entry(entry) for entry in entries]
            indexing.index_documents(index, chunk, wait=False)
            documents += chunk
    except indexing.IndexerNotInitializedError:
        pass
    except Exception:
        current_app.logger.error(
            "Indexer is not reachable, indexation failed.", exc_info=True
        )
    return documents


def _remove_entry_index(get_entry_index, document_id):
    """
    Remove the document that matches the given ID from its index. If the
    indexer is absent or cannot be reached, ignore the error.
    """
    try:
        return indexing.remove_document(get_entry_index(), document_id)
    except indexing.IndexerNotInitializedError:
        pass
    except Exception:
        current_app.logger.error(
            "Indexer is not reachable, indexation failed."
        )
    return {}


def reset_index():
    """
    Delete the asset, person and shot indexes and rebuild them from the
    database.
    """
    reset_asset_index()
    reset_person_index()
    reset_shot_index()


def reset_entry_index(
    index_name,
    get_entries,
    prepare_entry,
    searchable_fields=None,
    filterable_fields=None,
):
    """
    Create the index if necessary, clear it and rebuild it for the given
    parameters:
    - the name of the index,
    - the function that returns the entries to index,
    - the function that builds the document of an entry.
    Return the indexed entries.
    """
    if searchable_fields is None:
        searchable_fields = []
    if filterable_fields is None:
        filterable_fields = []
    index = indexing.create_index(
        index_name, searchable_fields, filterable_fields
    )
    indexing.clear_index(index_name)
    entries = get_entries()
    total = 0
    documents = []
    for entry in entries:
        documents.append(prepare_entry(entry))
        if len(documents) >= 3000:
            indexing.index_documents(index, documents)
            total += len(documents)
            documents = []
    if documents:
        indexing.index_documents(index, documents)
        total += len(documents)
    logger.info("%s %s indexed", total, index_name)
    return entries


def reset_asset_index():
    """
    Rebuild the asset index from the database.
    """
    reset_entry_index(
        "assets",
        get_all_raw_assets,
        prepare_asset,
        searchable_fields=["name", "description", "metadatas"],
        filterable_fields=["project_id"],
    )


def reset_person_index():
    """
    Rebuild the person index from the database.
    """
    reset_entry_index(
        "persons",
        get_all_raw_active_persons,
        prepare_person,
        searchable_fields=[
            "name",
        ],
    )


def reset_shot_index():
    """
    Rebuild the shot index from the database.
    """
    reset_entry_index(
        "shots",
        get_all_raw_shots,
        prepare_shot,
        searchable_fields=["name", "description", "metadatas"],
        filterable_fields=["project_id"],
    )


def search_assets(query, project_ids=None, limit=3, offset=0):
    """
    Search the index. The query is a simple string. Return a list of assets
    with more data, for example the project name and the asset type name. By
    default, return a maximum of 3 results.
    """
    if project_ids is None:
        project_ids = []
    index = get_asset_index()

    results = indexing.search(
        index, query, project_ids, limit=limit, offset=offset
    )
    if not results:
        return []

    asset_ids = [asset_id for asset_id, _ in results]

    # Get the assets in one batch, then collect the related IDs
    assets_raw = Entity.query.filter(Entity.id.in_(asset_ids)).all()
    assets_map = {str(e.id): e.serialize(obj_type="Asset") for e in assets_raw}

    project_ids_set = set()
    type_ids_set = set()
    preview_ids = set()
    for asset in assets_map.values():
        project_ids_set.add(asset["project_id"])
        type_ids_set.add(asset["entity_type_id"])
        if asset["preview_file_id"] is not None:
            preview_ids.add(asset["preview_file_id"])

    # Get the projects, asset types and preview files in one batch
    projects_map = {
        str(p.id): p.serialize()
        for p in Project.query.filter(
            Project.id.in_(list(project_ids_set))
        ).all()
    }
    types_map = {
        str(t.id): t.serialize(obj_type="AssetType")
        for t in EntityType.query.filter(
            EntityType.id.in_(list(type_ids_set))
        ).all()
    }
    previews_map = {}
    if preview_ids:
        previews_map = {
            str(p.id): p.serialize()
            for p in PreviewFile.query.filter(
                PreviewFile.id.in_(list(preview_ids))
            ).all()
        }

    # Assemble the results in the search order
    assets = []
    for asset_id, matched_terms in results:
        asset = assets_map.get(str(asset_id))
        if asset is None:
            continue
        asset_type = types_map.get(str(asset["entity_type_id"]), {})
        project = projects_map.get(str(asset["project_id"]), {})
        asset["project_name"] = project.get("name", "")
        asset["asset_type_name"] = asset_type.get("name", "")
        if asset["preview_file_id"] is not None:
            preview = previews_map.get(str(asset["preview_file_id"]))
            asset["preview_file_extension"] = (
                preview["extension"] if preview else None
            )
        else:
            asset["preview_file_extension"] = None
        asset["matched_terms"] = matched_terms
        assets.append(asset)
    return assets


def search_shots(query, project_ids=None, limit=3, offset=0):
    """
    Search the index. The query is a simple string. Return a list of shots
    with more data: the project name, the sequence name and, for a TV show,
    the episode. By default, return a maximum of 3 results.
    """
    if project_ids is None:
        project_ids = []
    index = get_shot_index()

    results = indexing.search(
        index, query, project_ids, limit=limit, offset=offset
    )
    if not results:
        return []

    shot_ids = [shot_id for shot_id, _ in results]

    # Get the shots in one batch
    shots_raw = Entity.query.filter(Entity.id.in_(shot_ids)).all()
    shots_map = {str(e.id): e.serialize(obj_type="Shot") for e in shots_raw}

    sequence_ids = set()
    project_ids_set = set()
    preview_ids = set()
    for shot in shots_map.values():
        if shot["parent_id"] is not None:
            sequence_ids.add(shot["parent_id"])
        project_ids_set.add(shot["project_id"])
        if shot["preview_file_id"] is not None:
            preview_ids.add(shot["preview_file_id"])

    # Get the sequences in one batch
    sequences_map = {}
    if sequence_ids:
        sequences_map = {
            str(e.id): e.serialize(obj_type="Sequence")
            for e in Entity.query.filter(
                Entity.id.in_(list(sequence_ids))
            ).all()
        }

    episode_ids = set()
    for seq in sequences_map.values():
        if seq.get("parent_id") is not None:
            episode_ids.add(seq["parent_id"])

    # Get the episodes in one batch
    episodes_map = {}
    if episode_ids:
        episodes_map = {
            str(e.id): e.serialize(obj_type="Episode")
            for e in Entity.query.filter(
                Entity.id.in_(list(episode_ids))
            ).all()
        }

    # Get the projects and preview files in one batch
    projects_map = {
        str(p.id): p.serialize()
        for p in Project.query.filter(
            Project.id.in_(list(project_ids_set))
        ).all()
    }
    previews_map = {}
    if preview_ids:
        previews_map = {
            str(p.id): p.serialize()
            for p in PreviewFile.query.filter(
                PreviewFile.id.in_(list(preview_ids))
            ).all()
        }

    # Assemble the results in the search order
    shots = []
    for shot_id, matched_terms in results:
        shot = shots_map.get(str(shot_id))
        if shot is None:
            continue
        sequence = sequences_map.get(str(shot["parent_id"]), {})
        project = projects_map.get(str(shot["project_id"]), {})
        shot["project_name"] = project.get("name", "")
        shot["sequence_name"] = sequence.get("name", "")
        if shot["preview_file_id"] is not None:
            preview = previews_map.get(str(shot["preview_file_id"]))
            shot["preview_file_extension"] = (
                preview["extension"] if preview else None
            )
        else:
            shot["preview_file_extension"] = None
        if projects_service.is_tv_show(project):
            episode_id = sequence.get("parent_id", None)
            if episode_id is not None:
                episode = episodes_map.get(str(episode_id))
                if episode:
                    shot["episode"] = episode["name"]
                    shot["episode_id"] = episode["id"]
        shot["matched_terms"] = matched_terms
        shots.append(shot)
    return shots


def search_persons(query, limit=3, offset=0, minimal=True):
    """
    Search the index. The query is a simple string. Return a list of persons.
    By default, return a maximum of 3 results. If minimal is set, show the
    persons as the /data/persons list shows them to a user who is not an
    admin.
    """
    index = get_person_index()
    results = indexing.search(index, query, limit=limit, offset=offset)
    if not results:
        return []

    person_ids = [person_id for person_id, _ in results]
    persons_map = {
        str(person.id): (
            person.present_minimal() if minimal else person.serialize_safe()
        )
        for person in Person.query.filter(Person.id.in_(person_ids)).all()
    }

    persons = []
    for person_id, matched_terms in results:
        person = persons_map.get(str(person_id))
        if person is None:
            continue
        person["matched_terms"] = matched_terms
        persons.append(person)
    return persons


def index_asset(asset):
    """
    Register the asset in the index.
    """
    return _index_entry(get_asset_index, prepare_asset, asset)


def index_person(person):
    """
    Register the person in the index. Never index preview accounts.
    """
    if person.preview_project_id is not None:
        return None
    return _index_entry(get_person_index, prepare_person, person)


def index_shot(shot):
    """
    Register the shot in the index.
    """
    return _index_entry(get_shot_index, prepare_shot, shot)


def index_assets(asset_ids):
    """
    Register the assets that match the given IDs in the index, in bulk.
    """
    return _index_entries(get_asset_index, prepare_asset, asset_ids)


def index_shots(shot_ids):
    """
    Register the shots that match the given IDs in the index, in bulk.
    """
    return _index_entries(get_shot_index, prepare_shot, shot_ids)


def prepare_metadatas(data):
    """
    Return the entity data that is useful for search: the values of its
    columns, stored as strings because the index has one type for each field.
    Leave out the keys of the built-in fields (frame range, trim handles...).
    """
    return {
        key: str(value)
        for key, value in (data or {}).items()
        if key not in metadata_descriptors_service.BUILT_IN_ENTITY_DATA_FIELDS
    }


def prepare_asset(asset):
    """
    Prepare an indexation document from the given asset.
    """
    asset_serialized = asset.serialize()
    asset_type = entity_types_service.get_asset_type(
        asset_serialized["entity_type_id"]
    )
    metadatas = prepare_metadatas(asset_serialized["data"])
    name = asset_serialized["name"]
    name = name + " " + name.replace("_", " ").replace("-", " ")
    name = asset_type["name"] + " " + name
    data = {
        "id": asset_serialized["id"],
        "name": name,
        "project_id": asset_serialized["project_id"],
        "episode_id": asset_serialized["source_id"] or "",
        "description": asset_serialized["description"],
        "metadatas": metadatas,
    }
    return data


def prepare_person(person):
    """
    Prepare an indexation document from the given person.
    """
    person_serialized = person.serialize()
    data = {
        "id": person_serialized["id"],
        "name": person_serialized["full_name"],
    }
    return data


def prepare_shot(shot):
    """
    Prepare an indexation document from the given shot.
    """
    shot_serialized = shot.serialize()

    episode_id = ""
    episode = None
    sequence = None
    sequence_id = shot_serialized.get("parent_id") or ""
    if sequence_id != "":
        # Read directly from the entity table. shots_service indexes through
        # this service, thus this service must not depend on it.
        sequence = Entity.get(sequence_id)
        if sequence is None:
            sequence_id = ""
        else:
            episode_id = sequence.parent_id and str(sequence.parent_id)
            if episode_id is not None:
                episode = Entity.get(episode_id)
                if episode is None:
                    episode_id = ""

    shot_name = shot_serialized["name"]
    name = shot_name + " " + shot_name.replace("_", " ").replace("-", " ")
    if episode is not None:
        name = f"{episode.name} {sequence.name} {name}"
    elif sequence is not None:
        name = f"{sequence.name} {name}"

    metadatas = prepare_metadatas(shot_serialized["data"])

    data = {
        "id": shot_serialized["id"],
        "name": name,
        "project_id": shot_serialized["project_id"],
        "sequence_id": sequence_id,
        "episode_id": episode_id,
        "description": shot_serialized["description"] or "",
        "metadatas": metadatas,
    }
    return data


def remove_asset_index(asset_id):
    """
    Remove the document that matches the given asset ID from the asset index.
    """
    return _remove_entry_index(get_asset_index, asset_id)


def remove_person_index(person_id):
    """
    Remove the document that matches the given person ID from the person
    index.
    """
    return _remove_entry_index(get_person_index, person_id)


def remove_shot_index(shot_id):
    """
    Remove the document that matches the given shot ID from the shot index.
    """
    return _remove_entry_index(get_shot_index, shot_id)


def get_all_raw_assets():
    """
    Return all assets from the database.
    """
    query = Entity.query.filter(entity_types_service.build_asset_type_filter())
    return query.all()


def get_all_raw_shots():
    """
    Return all shots from the database.
    """
    query = Entity.query.filter(
        Entity.entity_type_id == entity_types_service.get_shot_type()["id"]
    )
    return query.all()


def get_all_raw_active_persons():
    """
    Return all active persons without serialization. Exclude the guests and
    the preview accounts.
    """
    return Person.query.filter(
        Person.active,
        Person.is_guest.isnot(True),
        Person.preview_project_id.is_(None),
    ).all()
