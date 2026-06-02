import os
import time
import flask_fs

from contextlib import contextmanager

from flask import current_app
from werkzeug.utils import cached_property

from zou.app import config

from flask_fs.backends.local import LocalBackend

pictures = None
movies = None
files = None


_PROM_ENABLED = False
_OPS = _BYTES = _DURATION = _INFLIGHT = _ETAG_MISMATCH = None

try:
    from flask_fs.backends.swift import ETagMismatchError as _ETagMismatchError
except ImportError:
    _ETagMismatchError = None


if getattr(config, "PROMETHEUS_METRICS_ENABLED", False):
    try:
        from prometheus_client import Counter, Gauge, Histogram

        _OPS = Counter(
            "zou_storage_operations_total",
            "Storage operations by op, bucket and status",
            ["op", "bucket", "status"],
        )
        _BYTES = Counter(
            "zou_storage_bytes_total",
            "Bytes transferred for storage operations",
            ["op", "bucket"],
        )
        _DURATION = Histogram(
            "zou_storage_operation_duration_seconds",
            "Duration of storage operations in seconds",
            ["op", "bucket"],
            buckets=(
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2.5,
                5,
                10,
                30,
                60,
                120,
                300,
                600,
            ),
        )
        _INFLIGHT = Gauge(
            "zou_storage_operations_inflight",
            "In-flight storage operations",
            ["op", "bucket"],
            multiprocess_mode="livesum",
        )
        _ETAG_MISMATCH = Counter(
            "zou_storage_etag_mismatch_total",
            "ETag mismatches detected on Swift upload",
            ["bucket"],
        )
        _PROM_ENABLED = True
    except (ImportError, ValueError):
        _PROM_ENABLED = False


class _ByteTracker:
    """
    Mutable counter passed into ``_measure`` so streaming callers can
    accumulate transferred bytes incrementally before the context exits.
    """

    __slots__ = ("bytes",)

    def __init__(self):
        self.bytes = 0

    def add(self, n):
        self.bytes += n


def _is_etag_mismatch(exc):
    if _ETagMismatchError is not None and isinstance(exc, _ETagMismatchError):
        return True
    return "ETag mismatch" in str(exc)


@contextmanager
def _measure(op, bucket, byte_count=None, tracker=None):
    """
    Time a storage operation and record Prometheus metrics.

    Pass ``byte_count`` for ops that know the size up-front (upload).
    Pass ``tracker`` for streaming ops that accumulate bytes incrementally.
    Bytes are recorded only on success. Exceptions are classified as
    ``etag_mismatch`` (corruption detected by SwiftBackend) or ``error``.

    """
    if not _PROM_ENABLED:
        yield
        return
    start = time.monotonic()
    _INFLIGHT.labels(op=op, bucket=bucket).inc()
    status = "success"
    try:
        yield
    except Exception as exc:
        if _is_etag_mismatch(exc):
            status = "etag_mismatch"
            _ETAG_MISMATCH.labels(bucket=bucket).inc()
        else:
            status = "error"
        raise
    finally:
        _INFLIGHT.labels(op=op, bucket=bucket).dec()
        _OPS.labels(op=op, bucket=bucket, status=status).inc()
        _DURATION.labels(op=op, bucket=bucket).observe(
            time.monotonic() - start
        )
        if status == "success":
            n = (
                byte_count
                if byte_count is not None
                else (tracker.bytes if tracker is not None else None)
            )
            if n is not None:
                _BYTES.labels(op=op, bucket=bucket).inc(n)


def _safe_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def path(self, filename):
    folder_one = filename.split("-")[0]
    file_name = "-".join(filename.split("-")[1:])

    # Ensure root is absolute to avoid issues with relative paths
    root = (
        os.path.abspath(self.root)
        if not os.path.isabs(self.root)
        else self.root
    )

    if folder_one == "dbbackup":
        file_path = os.path.join(root, folder_one, file_name)
    else:
        folder_two = file_name[:3]
        folder_three = file_name[3:6]
        file_path = os.path.join(
            root, folder_one, folder_two, folder_three, file_name
        )
    # Normalize path to handle any remaining relative components
    return os.path.normpath(file_path)


LocalBackend.path = path


@cached_property
def _default_root(self):
    """
    Read the storage default root without opening a nested app context.

    The upstream LocalBackend wraps this in ``with current_app.app_context():``
    which, on teardown, triggers Flask-SQLAlchemy's ``db.session.remove()``
    handler. Since storage operations always happen inside a request that
    already has an app context, the nested context only serves to wipe the
    outer request's session and detach every loaded ORM instance.
    """
    default_root = current_app.config.get("FS_ROOT")
    return current_app.config.get("FS_LOCAL_ROOT", default_root)


LocalBackend.default_root = _default_root


def configure_storages(app):
    global pictures, movies, files
    pictures = make_storage("pictures")
    movies = make_storage("movies")
    files = make_storage("files")

    flask_fs.init_app(app, *[pictures, movies, files])


def clear_bucket(bucket):
    for filename in bucket.list_files():
        if isinstance(bucket.backend, LocalBackend):
            parts = filename.split("/")
            if len(parts) >= 2:
                bucket.delete(f"{parts[0]}-{parts[-1]}")
            else:
                bucket.delete(filename)
        else:
            bucket.delete(filename)


def make_key(prefix, id):
    return f"{prefix}-{id}"


@contextmanager
def _noop_measure():
    yield


def make_read_generator(bucket, key, bucket_name=None):
    """
    Create a generator that yields chunks from the storage bucket.
    This function ensures proper cleanup of the underlying stream to avoid
    reentrant call errors when the stream is accessed concurrently.

    When ``bucket_name`` is provided and Prometheus is enabled, the generator
    records a ``download`` operation with cumulative byte count.
    """
    read_stream = bucket.read_chunks(key)

    def read_generator(read_stream):
        tracker = _ByteTracker()
        measured = (
            _measure("download", bucket_name, tracker=tracker)
            if bucket_name is not None
            else _noop_measure()
        )
        try:
            with measured:
                for chunk in read_stream:
                    tracker.add(len(chunk))
                    yield chunk
        finally:
            if hasattr(read_stream, "close"):
                try:
                    read_stream.close()
                except Exception:
                    pass

    return read_generator(read_stream)


def make_storage(bucket):
    return flask_fs.Storage(
        f"{config.FS_BUCKET_PREFIX}{bucket}",
        overwrite=True,
    )


def clear():
    clear_bucket(pictures)
    clear_bucket(movies)
    clear_bucket(files)


def add_picture(prefix, id, path):
    key = make_key(prefix, id)
    with _measure("upload", "pictures", byte_count=_safe_size(path)):
        with open(path, "rb") as fd:
            return pictures.write(key, fd)


def get_picture(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "pictures"):
        data = pictures.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="pictures").inc(len(data))
    return data


def open_picture(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(pictures, key, bucket_name="pictures")


def read_picture(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "pictures"):
        data = pictures.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="pictures").inc(len(data))
    return data


def exists_picture(prefix, id):
    key = make_key(prefix, id)
    with _measure("exists", "pictures"):
        return pictures.exists(key)


def remove_picture(prefix, id):
    key = make_key(prefix, id)
    with _measure("delete", "pictures"):
        return pictures.delete(key)


def get_local_picture_path(prefix, id):
    return path(pictures, make_key(prefix, id))


def copy_picture(prefix, id, new_prefix, new_id):
    key = make_key(prefix, id)
    target = make_key(new_prefix, new_id)
    with _measure("copy", "pictures"):
        return pictures.copy(key, target)


def add_movie(prefix, id, path):
    key = make_key(prefix, id)
    with _measure("upload", "movies", byte_count=_safe_size(path)):
        with open(path, "rb") as fd:
            return movies.write(key, fd)


def get_movie(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "movies"):
        data = movies.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="movies").inc(len(data))
    return data


def open_movie(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(movies, key, bucket_name="movies")


def read_movie(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "movies"):
        data = movies.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="movies").inc(len(data))
    return data


def exists_movie(prefix, id):
    key = make_key(prefix, id)
    with _measure("exists", "movies"):
        return movies.exists(key)


def remove_movie(prefix, id):
    key = make_key(prefix, id)
    with _measure("delete", "movies"):
        return movies.delete(key)


def get_local_movie_path(prefix, id):
    return path(movies, make_key(prefix, id))


def copy_movie(prefix, id, new_prefix, new_id):
    key = make_key(prefix, id)
    target = make_key(new_prefix, new_id)
    with _measure("copy", "movies"):
        return movies.copy(key, target)


def add_file(prefix, id, path):
    key = make_key(prefix, id)
    with _measure("upload", "files", byte_count=_safe_size(path)):
        with open(path, "rb") as fd:
            return files.write(key, fd)


def get_file(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "files"):
        data = files.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="files").inc(len(data))
    return data


def open_file(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(files, key, bucket_name="files")


def read_file(prefix, id):
    key = make_key(prefix, id)
    with _measure("download", "files"):
        data = files.read(key)
    if _PROM_ENABLED and data is not None:
        _BYTES.labels(op="download", bucket="files").inc(len(data))
    return data


def exists_file(prefix, id):
    key = make_key(prefix, id)
    with _measure("exists", "files"):
        return files.exists(key)


def remove_file(prefix, id):
    key = make_key(prefix, id)
    with _measure("delete", "files"):
        return files.delete(key)


def get_local_file_path(prefix, id):
    return path(files, make_key(prefix, id))


def copy_file(prefix, id, new_prefix, new_id):
    key = make_key(prefix, id)
    target = make_key(new_prefix, new_id)
    with _measure("copy", "files"):
        return files.copy(key, target)
