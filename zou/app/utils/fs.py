import fcntl
import glob
import logging
import os
import shutil
import threading
import time
import uuid

from flask_fs.errors import FileNotFound

logger = logging.getLogger(__name__)

MAX_CONCURRENT_CACHE_FILLS = 4
_cache_fill_slots = threading.BoundedSemaphore(MAX_CONCURRENT_CACHE_FILLS)


MISSING_OBJECT_ERROR_CODES = {
    "404",
    "NoSuchKey",
    "NoSuchBucket",
    "NotFound",
}

# Pause before the single retry after a transient storage failure. The
# storage clients already do their own retries (FS_SWIFT_RETRIES, the
# retry mode of botocore), so this second chance must only outlast a short
# problem. A long pause here holds a request worker for nothing.
TRANSIENT_RETRY_DELAY = 0.5

STALE_PART_AGE = 3600


def mkdir_p(path):
    os.makedirs(path, exist_ok=True)


def rm_rf(path):
    if os.path.exists(path):
        shutil.rmtree(path)


def rm_file(path):
    if os.path.exists(path):
        os.remove(path)


def copyfile(src, dest):
    shutil.copyfile(src, dest)


def is_missing_file_error(exception):
    """
    Tell whether the error is a missing object, and not a transient
    storage failure.

    For a missing object, the file store raises FileNotFound with all
    backends. It lets the other failures through as they are: a Swift
    ClientException, a botocore ClientError. A retry for a missing object
    is not useful, and each request that falls back from one prefix to
    another pays the sleep of that retry.
    """
    if exception is None:
        return False
    if isinstance(exception, (FileNotFound, FileNotFoundError)):
        return True
    for attribute in ("http_status", "status", "status_code"):
        if getattr(exception, attribute, None) == 404:
            return True
    response = getattr(exception, "response", None)
    if isinstance(response, dict):
        metadata = response.get("ResponseMetadata") or {}
        if metadata.get("HTTPStatusCode") == 404:
            return True
        error = response.get("Error") or {}
        if error.get("Code") in MISSING_OBJECT_ERROR_CODES:
            return True
    return False


def is_range_error(exception):
    """
    Tell whether the error is a byte range that the object storage refused
    (416), and not an other failure.
    """
    for attribute in ("http_status", "status", "status_code"):
        if getattr(exception, attribute, None) == 416:
            return True
    response = getattr(exception, "response", None)
    if isinstance(response, dict):
        metadata = response.get("ResponseMetadata") or {}
        error = response.get("Error") or {}
        return (
            metadata.get("HTTPStatusCode") == 416
            or error.get("Code") == "InvalidRange"
        )
    return False


def is_auth_failure(exception):
    """
    Tell whether a Swift operation failed because Keystone could not
    give a token (for example, a 503 on the identity service).
    swiftclient raises this error with no HTTP status. Unlike a 5xx from
    Swift itself, swiftclient never retries it.
    """
    return getattr(exception, "http_status", "") is None and str(
        exception
    ).startswith("Authorization Failure")


class ConfirmedFileNotFound(FileNotFound):
    """
    The storage answered that the file does not exist: a 404, or a local
    file that is absent, empty or of the wrong size. A plain FileNotFound
    can also come from a transient failure that the retry did not solve.
    """


def is_confirmed_missing_error(exception):
    """
    Tell whether the storage itself confirmed the absence (a 404, or the
    missing-object code of an object store), and not an other failure.

    Unlike is_missing_file_error, this function does NOT accept a bare
    FileNotFoundError or FileNotFound as a confirmation. download_to_file
    also raises them for its own local temp file (TMP_DIR missing, or the
    .part that a concurrent _remove_stale_parts removed). These errors
    tell nothing about the remote object. Only an exception that the
    storage backend raised for a missing object confirms the absence:
    a ConfirmedFileNotFound, or an error with a 404 or a known
    missing-object code.
    """
    if exception is None:
        return False
    if isinstance(exception, ConfirmedFileNotFound):
        return True
    if isinstance(exception, (FileNotFound, FileNotFoundError)):
        return False
    for attribute in ("http_status", "status", "status_code"):
        if getattr(exception, attribute, None) == 404:
            return True
    response = getattr(exception, "response", None)
    if isinstance(response, dict):
        metadata = response.get("ResponseMetadata") or {}
        if metadata.get("HTTPStatusCode") == 404:
            return True
        error = response.get("Error") or {}
        if error.get("Code") in MISSING_OBJECT_ERROR_CODES:
            return True
    return False


def get_cache_file_path(config, prefix, instance_id, extension):
    """
    Return the path of the local copy of a file that a remote backend
    stores.
    """
    return os.path.join(
        config.TMP_DIR,
        f"cache-{prefix}-{instance_id}.{extension}",
    )


def _remove_stale_parts(file_path):
    """
    Remove the old .part files of `file_path`. If its process stops
    abruptly (OOM, SIGKILL, job timeout), a download does not get to its
    cleanup and leaves its .part file. A live download keeps the mtime of
    its .part recent, so it is safe to remove an old one.
    """
    for part_path in glob.glob(f"{glob.escape(file_path)}.*.part"):
        try:
            if time.time() - os.path.getmtime(part_path) > STALE_PART_AGE:
                os.remove(part_path)
        except OSError:
            pass


def download_to_file(file_path, open_file, prefix, instance_id):
    """
    Download a stored file to the local cache. Return the exception that
    stopped the download, or None. First, remove the old .part files
    that killed downloads left next to `file_path`.

    The bytes go into a private temporary file. When the download is
    complete, the function renames this file over the cache entry. A
    direct write into the cache entry would truncate the data that a
    concurrent request reads. It would also leave a partial file after
    an interruption. The size check of the cache accepts a truncated
    file as valid, so the server would send it as it is.
    """
    _remove_stale_parts(file_path)
    exception = None
    tmp_path = f"{file_path}.{uuid.uuid4().hex}.part"
    try:
        with open(tmp_path, "wb") as tmp_file:
            file_generator = open_file(prefix, instance_id)
            try:
                for chunk in file_generator:
                    tmp_file.write(chunk)
            finally:
                try:
                    file_generator.close()
                except (StopIteration, Exception):
                    pass
        os.replace(tmp_path, file_path)
    except Exception as e:
        exception = e
    finally:
        rm_file(tmp_path)
    return exception


def fill_cache_in_background(file_path, open_file, prefix, instance_id):
    """
    Download a file to the local cache from a background thread, unless
    another thread or worker process already does it. The downloader
    holds a flock on a sidecar lock file during the download. Return
    whether a download started. The lock file stays on disk: its removal
    would cause a race with the next locker.

    A worker runs a maximum of MAX_CONCURRENT_CACHE_FILLS fills at the
    same time. Without this limit, a playlist that prefetches each cold
    movie would start one thread for each movie. In all cases, the
    request streams the file from the storage. A refused fill only means
    that the next request tries again.
    """
    if not _cache_fill_slots.acquire(blocking=False):
        return False
    try:
        lock_file = open(f"{file_path}.lock", "a")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        # Another downloader holds the lock, or the cache directory is
        # full or read-only: no fill.
        _cache_fill_slots.release()
        return False

    def run():
        try:
            exception = download_to_file(
                file_path, open_file, prefix, instance_id
            )
            # A Keystone outage is transient and the request does not
            # depend on the fill: the next request fills the cache.
            if is_auth_failure(exception):
                logger.warning(
                    f"Cache fill failed for {prefix}-{instance_id}: "
                    f"{exception!r}"
                )
            elif exception is not None and not is_missing_file_error(
                exception
            ):
                logger.error(
                    f"Cache fill failed for {prefix}-{instance_id}: "
                    f"{exception!r}"
                )
        finally:
            lock_file.close()
            _cache_fill_slots.release()

    threading.Thread(target=run, daemon=True).start()
    return True


def get_file_path_and_file(
    config,
    get_local_path,
    open_file,
    prefix,
    instance_id,
    extension,
    file_size=None,
):
    """
    Return the local path of a stored file. On the local backend, this
    path is the stored file itself. On a remote backend, it is a cache
    entry. If the cache entry is absent or not valid, the function
    downloads it, with one retry after a transient failure. If the
    storage confirms that the file is missing (always true for a local
    file that is not valid), raise ConfirmedFileNotFound. If the download
    fails for an other reason, raise FileNotFound.
    """
    if config.FS_BACKEND == "local":
        file_path = get_local_path(prefix, instance_id)
        if is_invalid_file(file_path, file_size):
            raise ConfirmedFileNotFound(f"{prefix}-{instance_id}")
    else:
        file_path = get_cache_file_path(config, prefix, instance_id, extension)

        if is_invalid_file(file_path, file_size):
            exception = download_to_file(
                file_path, open_file, prefix, instance_id
            )
            # The code replaces the cache entry only as a whole, so a
            # concurrent request can complete it while this one fails.
            # Thus, examine the disk before a retry. If an object is not
            # there now, it will not be there a moment later. Only a
            # transient failure gets the retry: the movie routes try up
            # to three prefixes, and would else sleep on each missing
            # one.
            if is_invalid_file(
                file_path, file_size
            ) and not is_missing_file_error(exception):
                time.sleep(TRANSIENT_RETRY_DELAY)
                exception = download_to_file(
                    file_path, open_file, prefix, instance_id
                )

            if is_invalid_file(file_path, file_size):
                rm_file(file_path)
                if exception is not None:
                    if isinstance(exception, ConfirmedFileNotFound):
                        raise exception
                    if is_confirmed_missing_error(exception):
                        raise ConfirmedFileNotFound(
                            f"{prefix}-{instance_id}"
                        ) from exception
                    raise FileNotFound(
                        f"{prefix}-{instance_id}"
                    ) from exception
                else:
                    # The download reported success, but the file is
                    # still missing or empty. Treat it as absent (404),
                    # as the local backend does, not as an unhandled 500.
                    # This is not a confirmed absence: the storage did
                    # not say so.
                    raise FileNotFound(f"{prefix}-{instance_id}")

    return file_path


def is_invalid_file(file_path, file_size=None):
    """
    Tell whether the file is absent, is empty or does not match the
    given size.
    """
    if not os.path.exists(file_path):
        return True
    elif file_size is None:
        return get_file_size(file_path) == 0
    else:
        current_size = get_file_size(file_path)
        return current_size != file_size


def save_file(tmp_folder, instance_id, file_to_save):
    """
    Save the file in the given folder. Use this function only for a
    temporary save of the file.
    """
    extension = "." + file_to_save.filename.split(".")[-1].lower()
    file_name = instance_id + extension.lower()
    file_path = os.path.join(tmp_folder, file_name)
    file_to_save.save(file_path)
    return file_path


def get_file_extension(filename):
    """
    Return the extension of the given file name in lower case.
    """
    return filename.split(".")[-1].lower()


def get_file_size(file_path):
    """
    Return the size in bytes of the file at the given path.
    """
    return os.path.getsize(file_path)
