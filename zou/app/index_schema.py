import os

from zou.app.utils import fs, indexing
from zou.app import app

from whoosh.fields import NGRAMWORDS, ID, Schema, SchemaClass


asset_schema = Schema(
    name=NGRAMWORDS(minsize=3, maxsize=16, sortable=True, field_boost=20.0),
    description=NGRAMWORDS(
        minsize=3, maxsize=16, sortable=True, field_boost=10.0
    ),
    id=ID(unique=True, stored=True),
    project_id=ID(stored=True),
    episode_id=ID(stored=True),
)
asset_schema.add(
    "data_*", NGRAMWORDS(minsize=3, maxsize=16, sortable=True), glob=True
)


class PersonSchema(SchemaClass):
    name = NGRAMWORDS(minsize=3, maxsize=16, sortable=True)
    id = ID(unique=True, stored=True)


shot_schema = Schema(
    name=NGRAMWORDS(minsize=3, maxsize=16, sortable=True, field_boost=20.0),
    description=NGRAMWORDS(
        minsize=3, maxsize=16, sortable=True, field_boost=10.0
    ),
    id=ID(unique=True, stored=True),
    project_id=ID(stored=True),
    sequence_id=ID(stored=True),
)
shot_schema.add(
    "data_*", NGRAMWORDS(minsize=3, maxsize=16, sortable=True), glob=True
)

map_indexes_schema = {
    "assets": asset_schema,
    "shots": shot_schema,
    "persons": PersonSchema,
}


def init_indexes():
    indexes_folder = app.config["INDEXES_FOLDER"]
    indexes = {}
    for file_index_name, schema in map_indexes_schema.items():
        index_path = os.path.join(indexes_folder, file_index_name)
        indexes[file_index_name] = None
        if not os.path.exists(index_path):
            fs.mkdir_p(index_path)
        indexes[file_index_name] = indexing.create_index(index_path, schema)

    return indexes
