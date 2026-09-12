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


MISSING_OBJECT_ERROR_CODES = {
    "404",
    "NoSuchKey",
    "NoSuchBucket",
    "NotFound",
}


def is_missing_file_error(exception):
    """
    Tell a missing object apart from a transient storage failure.

    The file store raises FileNotFound for a missing object whatever the
    backend, and lets the other failures through as they are: a Swift
    ClientException, a botocore ClientError. Retrying a missing object is
    pointless, and the sleep it comes with is paid on every request that
    falls back from one prefix to another.
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
    Tell a byte range the object storage refused (416) from other failures.
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


def get_cache_file_path(config, prefix, instance_id, extension):
    """
    Path of the local copy kept for a file stored on a remote backend.
    """
    return os.path.join(
        config.TMP_DIR,
        f"cache-{prefix}-{instance_id}.{extension}",
    )


STALE_PART_AGE = 3600


def _remove_stale_parts(file_path):
    """
    A download killed with its process (OOM, SIGKILL, job timeout) never
    reaches its cleanup and leaves its .part behind. A live download
    keeps the mtime of its .part fresh, so an old one is safe to drop.
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
    interrupted it, or None.

    The bytes land in a private temporary file that is renamed over the
    cache entry once complete. Writing straight into it would truncate
    what a concurrent request is already reading, and would leave a
    partial file behind on any interruption: the size check that guards
    the cache accepts a truncated file as valid, so it would be served
    as is.
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
    another thread or worker process already is: the downloader holds a
    flock on a sidecar lock file for the duration. Return whether a
    download was started. The lock file is left behind: removing it would
    race with the next locker.

    A worker runs at most MAX_CONCURRENT_CACHE_FILLS fills at once: a
    playlist prefetching every cold movie would otherwise start one
    thread per movie. The request is streamed from the storage either
    way, a refused fill only means the next request tries again.
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
            if exception is not None and not is_missing_file_error(exception):
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
    if config.FS_BACKEND == "local":
        file_path = get_local_path(prefix, instance_id)
        if is_invalid_file(file_path, file_size):
            raise FileNotFound
    else:
        file_path = get_cache_file_path(config, prefix, instance_id, extension)

        if is_invalid_file(file_path, file_size):
            exception = download_to_file(
                file_path, open_file, prefix, instance_id
            )
            # The cache entry is only ever replaced as a whole, so a
            # concurrent request may well have completed it while this
            # one was failing: the disk is checked before paying for a
            # retry. An object that is not there will not be there three
            # seconds later either, only a transient failure deserves the
            # retry: the movie routes probe up to three prefixes and
            # would otherwise sleep on each missing one.
            if is_invalid_file(
                file_path, file_size
            ) and not is_missing_file_error(exception):
                time.sleep(3)
                exception = download_to_file(
                    file_path, open_file, prefix, instance_id
                )

            if is_invalid_file(file_path, file_size):
                rm_file(file_path)
                if exception is not None:
                    if isinstance(exception, FileNotFound):
                        raise exception
                    raise FileNotFound(
                        f"{prefix}-{instance_id}"
                    ) from exception
                else:
                    # The download reported success but the file is still
                    # missing or empty: treat it as absent (404) like the
                    # local backend does, not an unhandled 500.
                    raise FileNotFound(f"{prefix}-{instance_id}")

    return file_path


def is_invalid_file(file_path, file_size=None):
    """
    Check if file is absent, is empty or does match given size.
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
    Save file in given folder. The file must only be temporary saved via
    this function.
    """
    extension = "." + file_to_save.filename.split(".")[-1].lower()
    file_name = instance_id + extension.lower()
    file_path = os.path.join(tmp_folder, file_name)
    file_to_save.save(file_path)
    return file_path


def get_file_extension(filename):
    """
    Return extension of given file name in lower case.
    """
    return filename.split(".")[-1].lower()


def get_file_size(file_path):
    """
    Return in bytes the file size of the file located at given path.
    """
    return os.path.getsize(file_path)
