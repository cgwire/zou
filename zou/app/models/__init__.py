# PreviewFileStorageState has no CRUD blueprint and no route imports it,
# so nothing in the load_api() chain would otherwise register it with
# db.metadata before create_all() runs (at app creation, e.g. in
# tests/conftest.py). Import it here so the table always gets created.
from zou.app.models import preview_file_storage_state  # noqa: F401
