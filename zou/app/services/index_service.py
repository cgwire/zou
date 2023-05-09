from pathlib import Path

from zou.app.utils import indexing

from zou.app import app
from zou.app.index_schema import (
    init_indexes,
    map_indexes_schema,
)

from zou.app.services import (
    assets_service,
    persons_service,
    projects_service,
    shots_service,
    files_service,
)

from whoosh.index import EmptyIndexError


def get_index(index_name):
    """
    Retrieve whoosh index from disk. It is required to perform any operations.
    """
    try:
        return indexing.get_index(
            Path(app.config["INDEXES_FOLDER"]) / index_name
        )
    except EmptyIndexError:
        init_indexes()
        return indexing.get_index(
            Path(app.config["INDEXES_FOLDER"]) / index_name
        )


def get_asset_index():
    return get_index("assets")


def get_person_index():
    return get_index("persons")


def get_shot_index():
    return get_index("shots")


def reset_index():
    """
    Delete index and rebuild it by looping on all the assets listed in the
    database.
    """
    reset_asset_index()
    reset_person_index()
    reset_shot_index()


def reset_entry_index(index_name, get_entries, index_entry):
    """
    Clear and rebuild index for given parameters: folder name of the index, func to get entries to index, func to index a given entry.
    """
    index_path = Path(app.config["INDEXES_FOLDER"]) / index_name
    try:
        index = indexing.create_index(
            index_path, map_indexes_schema[index_name]
        )
    except FileNotFoundError:
        init_indexes()
        index = indexing.create_index(
            index_path, map_indexes_schema[index_name]
        )
    entries = get_entries()
    for entry in entries:
        index_entry(entry, index=index)
    print(len(entries), "%s indexed" % index_name)


def remove_entry_index(index, entry_id):
    """
    Remove document matching given id from given index.
    """
    entry_id = str(entry_id)
    index_writer = index.writer()
    index_writer.delete_by_term("id", entry_id)
    index_writer.commit()
    return entry_id


def reset_asset_index():
    reset_entry_index(
        "assets",
        assets_service.get_all_raw_assets,
        index_asset,
    )


def reset_person_index():
    reset_entry_index(
        "persons",
        persons_service.get_all_raw_active_persons,
        index_person,
    )


def reset_shot_index():
    reset_entry_index(
        "shots",
        shots_service.get_all_raw_shots,
        index_shot,
    )


def search_assets(query, project_ids=[], limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of assets with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_asset_index()
    fields = ["name", "description"]
    for field in index.reader().indexed_field_names():
        if field.startswith("data_"):
            fields.append(field)
    assets = []

    results = indexing.search(index, fields, query, project_ids, limit=limit)

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


def search_shots(query, project_ids=[], limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of shots with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_shot_index()
    fields = ["name", "description"]
    for field in index.reader().indexed_field_names():
        if field.startswith("data_"):
            fields.append(field)

    shots = []

    results = indexing.search(index, fields, query, project_ids, limit=limit)

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
            episode = shots_service.get_episode_from_sequence(sequence)
            shot["episode"] = episode["name"]
            shot["episode_id"] = episode["id"]
        shot["matched_terms"] = matched_terms
        shots.append(shot)
    return shots


def search_persons(query, limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of persons (3 results maximum by default).
    """
    index = get_person_index()
    fields = ["name"]

    persons = []
    results = indexing.search(index, fields, query, limit=limit)
    for person_id, matched_terms in results:
        person = persons_service.get_person(person_id)
        person["matched_terms"] = matched_terms
        persons.append(person)
    return persons


def index_asset(asset, index=None):
    """
    Register asset into the index.
    """
    if index is None:
        index = get_asset_index()
    asset_serialized = asset.serialize()
    metadatas = {}
    if asset_serialized["data"]:
        for k, v in asset_serialized["data"].items():
            metadatas[f"data_{k}"] = str(v)
    return indexing.index_data(
        index,
        {
            "name": asset_serialized["name"],
            "project_id": asset_serialized["project_id"],
            "episode_id": asset_serialized["source_id"],
            "id": asset_serialized["id"],
            "description": asset_serialized["description"],
            **metadatas,
        },
    )


def index_person(person, index=None):
    """
    Register person into the index.
    """
    if index is None:
        index = get_person_index()
    person_serialized = person.serialize()
    return indexing.index_data(
        index,
        {
            "name": person_serialized["full_name"],
            "id": person_serialized["id"],
        },
    )


def index_shot(shot, index=None):
    """
    Register shot into the index.
    """
    if index is None:
        index = get_shot_index()
    shot_serialized = shot.serialize()
    metadatas = {}
    if shot_serialized["data"]:
        for k, v in shot_serialized["data"].items():
            if k not in ["frame_in", "frame_out", "fps"]:
                metadatas[f"data_{k}"] = str(v)
    return indexing.index_data(
        index,
        {
            "name": shot_serialized["name"],
            "project_id": shot_serialized["project_id"],
            "sequence_id": shot_serialized["parent_id"],
            "id": shot_serialized["id"],
            "description": shot_serialized["description"],
            **metadatas,
        },
    )


def remove_asset_index(asset_id):
    """
    Remove document matching given asset id from asset index.
    """
    return remove_entry_index(get_asset_index(), asset_id)


def remove_person_index(person_id):
    """
    Remove document matching given person id from person index.
    """
    return remove_entry_index(get_person_index(), person_id)


def remove_shot_index(shot_id):
    """
    Remove document matching given shot id from shot index.
    """
    return remove_entry_index(get_shot_index(), shot_id)
