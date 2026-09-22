"""
State of the files stored for each preview file: present, confirmed
missing, or failed to be generated. Instance-local bookkeeping: it
describes this instance's storage, it is never synced between instances
nor serialized to the clients.
"""

import logging

from sqlalchemy.dialects.postgresql import insert

from zou.app import config, db
from zou.app.models.preview_file_storage_state import (
    PreviewFileStorageState,
)
from zou.app.utils import cache, date_helpers, fields

logger = logging.getLogger(__name__)

OK = "ok"
MISSING = "missing"
FAILED = "failed"

TILE = ("pictures", "tiles")
PICTURE_FILES = [
    ("pictures", "original"),
    ("pictures", "thumbnails"),
    ("pictures", "thumbnails-square"),
    ("pictures", "previews"),
]
MOVIE_FILES = [
    ("movies", "previews"),
    ("movies", "lowdef"),
    ("movies", "source"),
    *PICTURE_FILES,
    TILE,
]
GENERIC_FILES = [("files", "previews")]


def file_key(bucket, prefix):
    return f"{bucket}/{prefix}"


def get_expected_files(extension):
    """
    The stored files a preview file of given extension is made of.
    """
    if extension == "mp4":
        return list(MOVIE_FILES)
    if extension == "png":
        return list(PICTURE_FILES)
    return list(GENERIC_FILES)


def get_file_states(preview_file_id):
    """
    Known states of the stored files of a preview file, keyed by
    "bucket/prefix". A file never observed has no entry.
    """
    return _get_file_states(str(preview_file_id))


@cache.memoize_function(240)
def _get_file_states(preview_file_id):
    rows = PreviewFileStorageState.query.filter_by(
        preview_file_id=preview_file_id
    ).all()
    return {
        file_key(row.bucket, row.prefix): {
            "state": row.state.code,
            "updated_at": fields.serialize_value(row.updated_at),
        }
        for row in rows
    }


def clear_file_states_cache(preview_file_id):
    cache.cache.delete_memoized(_get_file_states, str(preview_file_id))


def get_state(states, bucket, prefix):
    entry = states.get(file_key(bucket, prefix))
    return entry["state"] if entry is not None else None


def is_known_missing(states, bucket, prefix):
    """
    True when the file was found missing, or failed to be generated, less
    than PREVIEW_MISSING_FILE_RECHECK_DELAY seconds ago.
    """
    entry = states.get(file_key(bucket, prefix))
    if entry is None or entry["state"] == OK:
        return False
    updated_at = date_helpers.get_datetime_from_string(entry["updated_at"])
    age = date_helpers.get_utc_now_datetime() - updated_at
    return age.total_seconds() < config.PREVIEW_MISSING_FILE_RECHECK_DELAY


def record_file_states(preview_file_id, states, refresh=False):
    """
    Record the states of stored files of a preview file, given as
    {(bucket, prefix): state}. Only the changes are written, unless
    refresh is set: an unchanged state then gets a new date, which keeps a
    file confirmed missing again short-circuited for another delay.

    The upsert itself is atomic (a single `INSERT ... ON CONFLICT`), so
    concurrent requests do not lose each other's writes. It emits no
    event and never raises: a lost state costs a storage round trip, not
    a request. Return whether anything was written.
    """
    preview_file_id = str(preview_file_id)
    if not refresh:
        known = get_file_states(preview_file_id)
        states = {
            (bucket, prefix): state
            for (bucket, prefix), state in states.items()
            if get_state(known, bucket, prefix) != state
        }
    if not states:
        return False
    now = date_helpers.get_utc_now_datetime()
    table = PreviewFileStorageState.__table__
    statement = insert(table).values(
        [
            {
                "id": fields.gen_uuid(),
                "preview_file_id": preview_file_id,
                "bucket": bucket,
                "prefix": prefix,
                "state": state,
                "created_at": now,
                "updated_at": now,
            }
            for (bucket, prefix), state in states.items()
        ]
    )
    upsert = statement.on_conflict_do_update(
        index_elements=["preview_file_id", "bucket", "prefix"],
        set_={
            "state": statement.excluded.state,
            "updated_at": statement.excluded.updated_at,
        },
        where=(None if refresh else table.c.state != statement.excluded.state),
    )
    try:
        db.session.execute(upsert)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning(
            f"Could not record the storage states of {preview_file_id}",
            exc_info=True,
        )
        return False
    finally:
        clear_file_states_cache(preview_file_id)
    return True


def record_file_state(preview_file_id, bucket, prefix, state, refresh=False):
    return record_file_states(
        preview_file_id, {(bucket, prefix): state}, refresh=refresh
    )
