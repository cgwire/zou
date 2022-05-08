from zou.app.utils import indexing
from zou.app.services import assets_service

from zou.app import app
from zou.app.index_schema import asset_schema


def reset_index():
    index = indexing.create_index(app.config["INDEXES_FOLDER"], asset_schema)
    # index = indexing.get_index(app.config["INDEXES_FOLDER"])

    for asset in assets_service.get_assets():
        indexing.index_data(index, {
            "name": asset["name"],
            "project_id": asset["project_id"],
            "id": asset["id"]
        })


def search_asset(query):
    index = indexing.get_index(app.config["INDEXES_FOLDER"])
    ids = indexing.search(index, query, limit=3)
    assets = []
    for asset_id in ids:
        assets.append(assets_service.get_asset(asset_id))
    print(assets)
    return assets
