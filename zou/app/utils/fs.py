import os
import shutil
import time
import uuid
from flask_fs.errors import FileNotFound


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

    Only the local backend raises FileNotFound: Swift surfaces its own
    ClientException and S3 a botocore ClientError, both carrying a 404.
    Retrying those is pointless, and the sleep it comes with is paid on
    every request that falls back from one prefix to another.
    """
    if exception is None:
        return False
    if isinstance(exception, FileNotFound):
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


def get_cache_file_path(config, prefix, instance_id, extension):
    """
    Path of the local copy kept for a file stored on a remote backend.
    """
    return os.path.join(
        config.TMP_DIR,
        f"cache-{prefix}-{instance_id}.{extension}",
    )


def _download_to_file(file_path, open_file, prefix, instance_id):
    """
    Download a stored file to the local cache.

    The bytes land in a private temporary file that is renamed over the
    cache entry once complete. Writing straight into it would truncate
    what a concurrent request is already reading, and would leave a
    partial file behind on any interruption: the size check that guards
    the cache accepts a truncated file as valid, so it would be served
    as is.
    """
    download_failed = False
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
        download_failed = True
        exception = e
    finally:
        rm_file(tmp_path)
    return download_failed, exception


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
            download_failed, exception = _download_to_file(
                file_path, open_file, prefix, instance_id
            )

            if is_invalid_file(file_path, file_size, download_failed):
                # An object that is not there will not be there three
                # seconds later. Only a transient failure deserves the
                # retry: the movie routes probe up to three prefixes and
                # would otherwise sleep on each missing one.
                if not is_missing_file_error(exception):
                    time.sleep(3)
                    download_failed, exception = _download_to_file(
                        file_path, open_file, prefix, instance_id
                    )

                if is_invalid_file(file_path, file_size, download_failed):
                    # The cache entry is only ever replaced as a whole, so
                    # a concurrent request may well have completed it while
                    # this one was failing.
                    if not is_invalid_file(file_path, file_size):
                        return file_path
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


def is_invalid_file(file_path, file_size=None, download_failed=False):
    """
    Check if file is absent, is empty or does match given size.
    """
    if download_failed or not os.path.exists(file_path):
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
