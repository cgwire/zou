"""
Registry of the objects written to the file storage. Every write records
the object, every deletion marks it: the object itself is removed later
by a purge job, outside of the request that deleted it. Instance-local
bookkeeping: it describes this instance's storage, it is never synced
between instances nor serialized to the clients.
"""

import logging

from datetime import timedelta

from sqlalchemy import tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from zou.app import config, db
from zou.app.models.stored_file import StoredFile
from zou.app.utils import date_helpers, fields

logger = logging.getLogger(__name__)

# Entries kept in the journal of an object: an avatar rewritten every day
# must not grow its row forever.
JOURNAL_MAX_LENGTH = 50


def make_key(prefix, file_id):
    """
    Same layout as file_store.make_key, which cannot be imported here:
    the file store calls this service.
    """
    return f"{prefix}-{file_id}"


def _session():
    """
    A session of its own, on a dedicated connection: the registry commits
    and rolls back without touching the changes the caller has not
    committed yet. Rows stay readable once it is closed.
    """
    return Session(db.engine, expire_on_commit=False)


def _lock(session, files, now):
    """
    Create the rows of the given (bucket, prefix, file_id) objects that
    are unknown, then lock them all until the end of the transaction.
    They are locked in key order, so that two transactions on the same
    objects cannot deadlock. Return the rows in that order.
    """
    files = {
        (bucket, make_key(prefix, file_id)): (bucket, prefix, str(file_id))
        for bucket, prefix, file_id in files
    }
    session.execute(
        insert(StoredFile.__table__)
        .values(
            [
                {
                    "id": fields.gen_uuid(),
                    "bucket": bucket,
                    "key": key,
                    "prefix": prefix,
                    "file_id": file_id,
                    "purge_forced": False,
                    "purge_attempts": 0,
                    "journal": [],
                    "created_at": now,
                    "updated_at": now,
                }
                for (bucket, key), (_, prefix, file_id) in files.items()
            ]
        )
        .on_conflict_do_nothing(index_elements=["bucket", "key"])
    )
    return (
        session.query(StoredFile)
        .filter(tuple_(StoredFile.bucket, StoredFile.key).in_(list(files)))
        .order_by(StoredFile.bucket, StoredFile.key)
        .with_for_update()
        .all()
    )


def _append(stored_file, entry, now):
    entry["at"] = now.isoformat()
    journal = list(stored_file.journal or []) + [entry]
    stored_file.journal = journal[-JOURNAL_MAX_LENGTH:]
    stored_file.updated_at = now


def _describe(files):
    return ", ".join(
        f"{bucket}/{make_key(prefix, file_id)}"
        for bucket, prefix, file_id in files
    )


def _change(files, apply_change):
    """
    Lock the rows of the given (bucket, prefix, file_id) objects,
    creating the unknown ones, then let apply_change update each row and
    return the journal entry to append. One transaction for them all.
    The lock keeps a deletion, a purge and a new write of the same key
    from interleaving. Never raises: losing a registry entry must not
    fail the storage operation it describes. Return the rows, or None on
    failure.
    """
    if not files:
        return []
    now = date_helpers.get_utc_now_datetime()
    try:
        with _session() as session, session.begin():
            stored_files = _lock(session, files, now)
            for stored_file in stored_files:
                _append(stored_file, apply_change(stored_file, now), now)
        return stored_files
    except Exception:
        logger.error(
            f"Could not record the change of stored files {_describe(files)}",
            exc_info=True,
        )
        return None


def record_writes(files, size=None):
    """
    Record that the given (bucket, prefix, file_id) objects are being
    written. Writing a key marked deleted revives it, so that the purge
    job does not remove a file that is in use again (an avatar removed
    then uploaded again keeps its key). Callers record before writing the
    object: a purge running at the same time either removes the old
    object before the write, or finds the row revived and leaves it
    alone.
    """

    def apply_change(stored_file, now):
        if stored_file.deleted_at is not None:
            op = "undelete" if stored_file.purged_at is None else "create"
            stored_file.deleted_at = None
            stored_file.purged_at = None
            stored_file.purge_forced = False
            stored_file.purge_attempts = 0
            stored_file.last_error = None
        else:
            op = "create" if not stored_file.journal else "update"
        if size is not None:
            stored_file.size = size
        entry = {"op": op}
        if size is not None:
            entry["size"] = size
        return entry

    return _change(files, apply_change)


def record_write(bucket, prefix, file_id, size=None):
    """
    Record that one object is being written, see record_writes.
    """
    return record_writes([(bucket, prefix, file_id)], size=size)


def record_remote_writes(files):
    """
    Record the objects a remote worker is about to write straight to the
    storage, given as (bucket, prefix, file_id) triples: they never go
    through the file store. Recorded before the job runs, so that the
    objects a failed job leaves behind are known too: a row whose object
    never got written is harmless, a missing object counts as purged.
    """
    return record_writes(files)


def mark_deleted(files, force=False):
    """
    Mark the given (bucket, prefix, file_id) objects deleted. The purge
    removes them if REMOVE_FILES is set, or whatever the setting if force
    is. An object written before the registry existed gets its row now,
    its creation date being the date of the deletion.
    """

    def apply_change(stored_file, now):
        if stored_file.deleted_at is None:
            stored_file.deleted_at = now
        stored_file.purge_forced = stored_file.purge_forced or force
        return {"op": "delete", "force": force}

    return _change(files, apply_change)


def _is_purgeable(stored_file):
    return (
        stored_file.deleted_at is not None
        and stored_file.purged_at is None
        and (stored_file.purge_forced or config.REMOVE_FILES)
    )


def purge(files, remove_object):
    """
    Remove the given (bucket, prefix, file_id) objects from the storage
    through remove_object(bucket, prefix, file_id), and record it, in a
    single transaction. The rows stay locked while the objects are
    removed, and are checked again under the lock: an object revived by
    a new write, or that the purge is no longer allowed to remove, is
    left alone. A failure is recorded for the purge job to try again.
    Never raises. Return the set of (bucket, key) removed.
    """
    if not files:
        return set()
    keys = {
        (bucket, make_key(prefix, file_id))
        for bucket, prefix, file_id in files
    }
    now = date_helpers.get_utc_now_datetime()
    removed = set()
    try:
        with _session() as session, session.begin():
            stored_files = (
                session.query(StoredFile)
                .filter(tuple_(StoredFile.bucket, StoredFile.key).in_(keys))
                .order_by(StoredFile.bucket, StoredFile.key)
                .with_for_update()
                .all()
            )
            for stored_file in stored_files:
                if not _is_purgeable(stored_file):
                    continue
                try:
                    remove_object(
                        stored_file.bucket,
                        stored_file.prefix,
                        stored_file.file_id,
                    )
                except Exception as exc:
                    logger.warning(
                        f"Stored file {stored_file.bucket}/"
                        f"{stored_file.key} could not be removed.",
                        exc_info=True,
                    )
                    stored_file.purge_attempts = (
                        stored_file.purge_attempts or 0
                    ) + 1
                    stored_file.last_error = str(exc)
                    _append(stored_file, {"op": "purge_failed"}, now)
                    continue
                stored_file.purged_at = now
                stored_file.last_error = None
                _append(stored_file, {"op": "purge"}, now)
                removed.add((stored_file.bucket, stored_file.key))
        return removed
    except Exception:
        logger.error(
            f"Could not purge stored files {_describe(files)}", exc_info=True
        )
        return set()


def get_files_to_purge(limit=100, grace_delay=0):
    """
    Objects marked deleted at least grace_delay seconds ago, not purged
    yet, that the purge is allowed to remove. The oldest come first.
    """
    deleted_before = date_helpers.get_utc_now_datetime() - timedelta(
        seconds=grace_delay
    )
    query = StoredFile.query.filter(
        StoredFile.deleted_at.isnot(None),
        StoredFile.purged_at.is_(None),
        StoredFile.deleted_at <= deleted_before,
    )
    if not config.REMOVE_FILES:
        query = query.filter(StoredFile.purge_forced.is_(True))
    return [
        stored_file.serialize()
        for stored_file in query.order_by(StoredFile.deleted_at)
        .limit(limit)
        .all()
    ]


def get_stored_file(bucket, prefix, file_id):
    stored_file = StoredFile.get_by(
        bucket=bucket, key=make_key(prefix, file_id)
    )
    return stored_file.serialize() if stored_file is not None else None
