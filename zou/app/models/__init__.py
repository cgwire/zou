# PreviewFileStorageState and StoredFile have no CRUD blueprint, and no route
# imports them. Without this import, nothing in the load_api() chain registers
# them with db.metadata before create_all() runs (at app creation, for example
# in tests/conftest.py). This import makes sure that Zou always creates the
# tables.
from zou.app.models import preview_file_storage_state  # noqa: F401
from zou.app.models import stored_file  # noqa: F401
