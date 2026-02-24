import os
import shutil
import time
from flask_fs.errors import FileNotFound


class DownloadFromStorageFailedException(Exception):
    pass


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


def _download_to_file(file_path, open_file, prefix, instance_id):
    download_failed = False
    exception = None
    try:
        with open(file_path, "wb") as tmp_file:
            file_generator = open_file(prefix, instance_id)
            try:
                for chunk in file_generator:
                    tmp_file.write(chunk)
            finally:
                try:
                    file_generator.close()
                except (StopIteration, Exception):
                    pass
    except Exception as e:
        download_failed = True
        exception = e
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
        file_path = os.path.join(
            config.TMP_DIR,
            f"cache-{prefix}-{instance_id}.{extension}",
        )

        if is_invalid_file(file_path, file_size):
            download_failed, exception = _download_to_file(
                file_path, open_file, prefix, instance_id
            )

            if is_invalid_file(file_path, file_size, download_failed):
                time.sleep(3)
                download_failed, exception = _download_to_file(
                    file_path, open_file, prefix, instance_id
                )

                if is_invalid_file(file_path, file_size, download_failed):
                    rm_file(file_path)
                    if exception is not None:
                        raise exception
                    else:
                        raise DownloadFromStorageFailedException

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
