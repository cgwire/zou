"""
Registry of the objects written to the file storage. Each write records
the object, and each deletion marks it. A purge job removes the object
later, outside of the request that deleted it. This registry is local to
the instance: it describes the storage of this instance. It is not
synchronized between instances and not serialized to the clients.
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

# Maximum number of entries in the journal of an object. The row of an
# avatar that is written again each day must not grow without limit.
JOURNAL_MAX_LENGTH = 50


def make_key(prefix, file_id):
    """
    Return the key of an object, with the same layout as
    file_store.make_key. This module cannot import file_store, because the
    file store calls this service.
    """
    return f"{prefix}-{file_id}"


def _session():
    """
    Return a new session on a dedicated connection. Thus the registry can
    commit and roll back, and the changes that the caller did not commit
    yet stay as they are. The rows stay readable after the session closes.
    """
    return Session(db.engine, expire_on_commit=False)


def _lock(session, files, now):
    """
    Create the missing rows of the given (bucket, prefix, file_id)
    objects. Then lock all the rows until the end of the transaction. The
    lock order is the key order, thus two transactions on the same objects
    cannot deadlock. Return the rows in that order.
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
    Lock the rows of the given (bucket, prefix, file_id) objects, and
    create the missing rows. Then apply_change updates each row and
    returns the journal entry to add. All the rows use one transaction.
    The lock prevents the interleave of a deletion, a purge and a new
    write of the same key. This function does not raise: the loss of a
    registry entry must not make the related storage operation fail.
    Return the rows. If a failure occurs, return None.
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
    Record the write of the given (bucket, prefix, file_id) objects. A
    write of a key that is marked deleted revives it. Thus the purge job
    does not remove a file that is in use again. For example, an avatar
    that is removed and then uploaded again keeps its key. Callers record
    before they write the object. A purge that runs at the same time
    removes the old object before the write, or it finds the revived row
    and does not change it.
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
    Record the write of one object. See record_writes.
    """
    return record_writes([(bucket, prefix, file_id)], size=size)


def record_remote_writes(files):
    """
    Record the objects that a remote worker will write directly to the
    storage, given as (bucket, prefix, file_id) triples. These objects do
    not go through the file store. Record them before the job starts. Thus
    the registry also knows the objects that a failed job leaves. A row
    without a written object causes no problem: a missing object counts
    as purged.
    """
    return record_writes(files)


def mark_deleted(files, force=False):
    """
    Mark the given (bucket, prefix, file_id) objects as deleted. If
    REMOVE_FILES is set, the purge removes them. If force is set, the
    purge removes them with all values of REMOVE_FILES. If an object was
    written before the registry existed, it gets its row now. The creation
    date of this row is the date of the deletion.
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
    with remove_object(bucket, prefix, file_id), and record the removal.
    Use one transaction. The rows stay locked during the removal, and
    the purge examines them again under the lock. The purge does not
    remove an object that a new write revived, or an object that the
    purge must not remove now. The purge records a failure, so that the
    purge job can try again. This function does not raise. Return the
    set of the removed (bucket, key) pairs.
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
    Return the objects that the purge can remove, as dicts. These objects
    were marked deleted grace_delay seconds ago or more, and are not
    purged yet. The oldest objects come first. Return limit objects or
    less.
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
