from pathlib import Path

from zou.app.utils import indexing

from zou.app import app
from zou.app.index_schema import asset_schema, person_schema, init_indexes

from zou.app.services import assets_service, persons_service, projects_service

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


def reset_index():
    """
    Delete index and rebuild it by looping on all the assets listed in the
    database.
    """
    reset_asset_index()
    reset_person_index()


def reset_entry_index(index_name, schema, get_entries, index_entry):
    """
    Clear and rebuild index for given parameters: folder name of the index,
    schema, func to get entries to index, func to index a given entry.
    """
    index_path = Path(app.config["INDEXES_FOLDER"]) / index_name
    try:
        index = indexing.create_index(index_path, schema)
    except FileNotFoundError:
        init_indexes()
        index = indexing.create_index(index_path, schema)
    entries = get_entries()
    for entry in entries:
        index_entry(entry, index=index)
    print(len(entries), "%s indexed" % index_name)


def remove_entry_index(index, entry_id):
    """
    Remove document matching given id from given index.
    """
    index_writer = index.writer()
    index_writer.delete_by_term("id", entry_id)
    index_writer.commit()
    return entry_id


def reset_asset_index():
    reset_entry_index(
        "assets", asset_schema, assets_service.get_all_raw_assets, index_asset
    )


def reset_person_index():
    reset_entry_index(
        "persons",
        person_schema,
        persons_service.get_all_raw_active_persons,
        index_person,
    )


def search_assets(query, project_ids=[], limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of assets with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_asset_index()
    assets = []

    ids = indexing.search(index, query, project_ids, limit=limit)

    for asset_id in ids:
        asset = assets_service.get_asset(asset_id)
        asset_type = assets_service.get_asset_type(asset["entity_type_id"])
        project = projects_service.get_project(asset["project_id"])
        asset["project_name"] = project["name"]
        asset["asset_type_name"] = asset_type["name"]
        assets.append(asset)
    return assets


def search_persons(query, limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of persons (3 results maximum by default).
    """
    index = get_person_index()
    persons = []
    ids = indexing.search(index, query, limit=limit)
    for person_id in ids:
        person = persons_service.get_person(person_id)
        persons.append(person)
    return persons


def index_asset(asset, index=None):
    """
    Register asset into the index.
    """
    if index is None:
        index = get_asset_index()
    return indexing.index_data(
        index,
        {
            "name": asset.name,
            "project_id": str(asset.project_id),
            "episode_id": str(asset.source_id),
            "id": str(asset.id),
        },
    )


def index_person(person, index=None):
    """
    Register person into the index.
    """
    if index is None:
        index = get_person_index()
    return indexing.index_data(
        index, {"name": person.full_name(), "id": str(person.id)}
    )


def remove_asset_index(asset_id):
    """
    Remove document matching given asset id from asset index.
    """
    return remove_entry_index(get_asset_index(), str(asset_id))


def remove_person_index(person_id):
    """
    Remove document matching given person id from person index.
    """
    return remove_entry_index(get_person_index(), str(person_id))
