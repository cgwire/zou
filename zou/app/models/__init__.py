# PreviewFileStorageState and StoredFile have no CRUD blueprint and no
# route imports them, so nothing in the load_api() chain would otherwise
# register them with db.metadata before create_all() runs (at app
# creation, e.g. in tests/conftest.py). Import them here so the tables
# always get created.
from zou.app.models import preview_file_storage_state  # noqa: F401
from zou.app.models import stored_file  # noqa: F401
