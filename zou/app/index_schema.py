import os

from zou.app.utils import fs, indexing

asset_schema = indexing.get_schema(
    {
        "name": "indexed",
        "id": "unique_id_stored",
        "project_id": "id_stored",
        "episode_id": "id_stored",
    }
)

person_schema = indexing.get_schema(
    {"name": "indexed", "id": "unique_id_stored"}
)


def init_indexes(index_folder):
    index_path = os.path.join(index_folder, "assets")
    asset_index = None
    if not os.path.exists(index_path):
        fs.mkdir_p(index_path)
        asset_index = indexing.create_index(index_path, asset_schema)
    person_index_path = os.path.join(index_folder, "persons")
    person_index = None
    if not os.path.exists(person_index_path):
        fs.mkdir_p(person_index_path)
        person_index = indexing.create_index(person_index_path, person_schema)
    return (asset_index, person_index)
