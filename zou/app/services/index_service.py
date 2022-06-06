from pathlib import Path

from zou.app.utils import indexing

from zou.app import app
from zou.app.index_schema import asset_schema
from zou.app.utils import permissions

from zou.app.services import (
    assets_service,
    projects_service,
    user_service
)


def get_index():
    """
    Retrieve whoosh index from disk. It is required to perform any operations.
    """
    return indexing.get_index(Path(app.config["INDEXES_FOLDER"]) / "assets")


def reset_index():
    """
    Delete index and rebuild it by looping on all the assets listed in the
    database.
    """
    index_path = Path(app.config["INDEXES_FOLDER"]) / "assets"
    index = indexing.create_index(index_path, asset_schema)
    assets = assets_service.get_all_raw_assets()
    for asset in assets:
        index_asset(asset, index=index)
    print(len(assets), "assets indexed")


def search_assets(query, project_ids=[], limit=3):
    """
    Perform a search on the index. The query is a simple string. The result is
    a list of assets with extra data like the project name and the asset type
    name (3 results maximum by default).
    """
    index = get_index()
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


def index_asset(asset, index=None):
    """
    Register asset into the index.
    """
    if index is None:
        index = get_index()
    return indexing.index_data(index, {
        "name": asset.name,
        "project_id": str(asset.project_id),
        "episode_id": str(asset.source_id),
        "id": str(asset.id)
    })


def remove_asset_index(asset_id):
    """
    Remove document matching given asset id.
    """
    index_writer = get_index().writer()
    index_writer.delete_by_term("id", asset_id)
    index_writer.commit()
    return asset_id
