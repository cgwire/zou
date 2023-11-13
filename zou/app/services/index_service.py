from zou.app import app
from zou.app.indexer import indexing

from zou.app.services import (
    assets_service,
    persons_service,
    projects_service,
    shots_service,
    files_service,
)


def get_index(index_name):
    """
    Retrieve whoosh index from disk. It is required to perform any operations.
    """
    indexing.init()
    return indexing.get_index(index_name)


def get_asset_index():
    return get_index("assets")


def get_person_index():
    return get_index("persons")


def get_shot_index():
    return get_index("shots")


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def reset_index():
    """
    Delete index and rebuild it by looping on all the assets listed in the
    database.
    """
    reset_asset_index()
    reset_person_index()
    reset_shot_index()


def reset_entry_index(
    index_name,
    get_entries,
    prepare_entry,
    searchable_fields=[],
    filterable_fields=[],
):
    """
    Clear and rebuild index for given parameters: folder name of the index,
    func to get entries to index, func to index a given entry.
    """
    index = indexing.create_index(
        index_name, searchable_fields, filterable_fields
    )
    indexing.clear_index(index_name)
    entries = get_entries()
    documents = []
    for chunk in chunks(entries, 3000):
        for entry in chunk:
            document = prepare_entry(entry)
            documents.append(document)
        indexing.index_documents(index, documents)
    print(len(entries), "%s indexed" % index_name)
    return entries


def reset_asset_index():
    reset_entry_index(
        "assets",
        assets_service.get_all_raw_assets,
        prepare_asset,
        searchable_fields=["name", "description", "metadatas"],
        filterable_fields=["project_id"],
    )


def reset_person_index():
    reset_entry_index(
        "persons",
        persons_service.get_all_raw_active_persons,
        prepare_person,
        searchable_fields=[
            "name",
        ],
    )


def reset_shot_index():
    reset_entry_index(
        "shots",
        shots_service.get_all_raw_shots,
        prepare_shot,
        searchable_fields=["name", "description", "metadatas"],
        filterable_fields=["project_id"],
    )


def search_assets(query, project_ids=[], limit=3, offset=0):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of assets with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_asset_index()
    assets = []

    results = indexing.search(
        index, query, project_ids, limit=limit, offset=offset
    )
    for asset_id, matched_terms in results:
        asset = assets_service.get_asset(asset_id)
        asset_type = assets_service.get_asset_type(asset["entity_type_id"])
        project = projects_service.get_project(asset["project_id"])
        asset["project_name"] = project["name"]
        asset["asset_type_name"] = asset_type["name"]
        if asset["preview_file_id"] is not None:
            preview_file = files_service.get_preview_file(
                asset["preview_file_id"]
            )
            asset["preview_file_extension"] = preview_file["extension"]
        else:
            asset["preview_file_extension"] = None
        asset["matched_terms"] = matched_terms
        assets.append(asset)
    return assets


def search_shots(query, project_ids=[], limit=3, offset=0):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of shots with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_shot_index()
    shots = []

    results = indexing.search(
        index, query, project_ids, limit=limit, offset=offset
    )

    for shot_id, matched_terms in results:
        shot = shots_service.get_shot(shot_id)
        sequence = shots_service.get_sequence(shot["parent_id"])
        project = projects_service.get_project(shot["project_id"])
        shot["project_name"] = project["name"]
        shot["sequence_name"] = sequence["name"]
        if shot["preview_file_id"] is not None:
            preview_file = files_service.get_preview_file(
                shot["preview_file_id"]
            )
            shot["preview_file_extension"] = preview_file["extension"]
        else:
            shot["preview_file_extension"] = None
        if projects_service.is_tv_show(project):
            episode_id = sequence.get("parent_id", None)
            if episode_id is not None:
                episode = shots_service.get_episode(episode_id)
                shot["episode"] = episode["name"]
                shot["episode_id"] = episode["id"]
        shot["matched_terms"] = matched_terms
        shots.append(shot)
    return shots


def search_persons(query, limit=3, offset=0):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of persons (3 results maximum by default).
    """
    index = get_person_index()
    persons = []
    results = indexing.search(index, query, limit=limit, offset=offset)
    for person_id, matched_terms in results:
        person = persons_service.get_person(person_id)
        person["matched_terms"] = matched_terms
        persons.append(person)
    return persons


def index_asset(asset):
    """
    Register asset into the index.
    """
    try:
        index = get_asset_index()
        document = prepare_asset(asset)
        indexing.index_document(index, document)
        return document
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}


def index_person(person):
    """
    Register person into the index.
    """
    try:
        index = get_person_index()
        document = prepare_person(person)
        indexing.index_document(index, document)
        return document
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}


def index_shot(shot):
    """
    Register shot into the index.
    """
    try:
        index = get_shot_index()
        document = prepare_shot(shot)
        indexing.index_document(index, document)
        return document
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}


def prepare_asset(asset):
    """
    Prepare a indexation document from given asset.
    """
    asset_serialized = asset.serialize()
    asset_type = assets_service.get_asset_type(
        asset_serialized["entity_type_id"]
    )
    metadatas = {}
    if asset_serialized["data"]:
        for k, v in asset_serialized["data"].items():
            metadatas[f"{k}"] = str(v)
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


def prepare_person(person, index=None):
    """
    Prepare a indexation document from given person.
    """
    if index is None:
        index = get_person_index()
    person_serialized = person.serialize()
    data = {
        "id": person_serialized["id"],
        "name": person_serialized["full_name"],
    }
    return data


def prepare_shot(shot, index=None):
    """
    Prepare a indexation document from given shot.
    """
    if index is None:
        index = get_shot_index()
    shot_serialized = shot.serialize()

    episode_id = ""
    episode = None
    sequence_id = shot_serialized.get("parent_id", "")
    if sequence_id != "":
        sequence = shots_service.get_sequence(sequence_id)
        episode_id = sequence.get("parent_id", "")
        if episode_id not in ["", "None", None]:
            episode = shots_service.get_episode(episode_id)

    shot_name = shot_serialized["name"]
    name = shot_name + " " + shot_name.replace("_", " ").replace("-", " ")
    if episode is not None:
        shot_name = f'{episode["name"]} {sequence["name"]} {name}'
    else:
        shot_name = f'{sequence["name"]} {name}'

    metadatas = {}
    if shot_serialized["data"]:
        for k, v in shot_serialized["data"].items():
            if k not in [
                "frame_in",
                "frame_out",
                "fps",
                "handle_in",
                "handle_out",
            ]:
                metadatas[f"{k}"] = str(v)

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
    Remove document matching given asset id from asset index.
    """
    try:
        return indexing.remove_document(get_asset_index(), asset_id)
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}


def remove_person_index(person_id):
    """
    Remove document matching given person id from person index.
    """
    try:
        return indexing.remove_document(get_person_index(), person_id)
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}


def remove_shot_index(shot_id):
    """
    Remove document matching given shot id from shot index.
    """
    try:
        return indexing.remove_document(get_shot_index(), shot_id)
    except:
        app.logger.error("Indexer is not reachable, indexation failed.")
        return {}
