from zou.app.utils import indexing

asset_schema = indexing.get_schema({
    "name": "indexed",
    "id": "unique_id_stored",
    "project_id": "id_stored",
    "episode_id": "id_stored",
})
