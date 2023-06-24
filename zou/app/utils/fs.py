import os
import shutil
import time

import errno


class DownloadFromStorageFailedException(Exception):
    pass


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def rm_rf(path):
    if os.path.exists(path):
        shutil.rmtree(path)


def rm_file(path):
    if os.path.exists(path):
        os.remove(path)


def copyfile(src, dest):
    shutil.copyfile(src, dest)


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
    else:
        file_path = os.path.join(
            config.TMP_DIR, "cache-%s-%s.%s" % (prefix, instance_id, extension)
        )

        if is_unvalid_file(file_path, file_size):
            download_failed = False
            exception = None
            try:
                with open(file_path, "wb") as tmp_file:
                    for chunk in open_file(prefix, instance_id):
                        tmp_file.write(chunk)
            except:
                download_failed = True

            if is_unvalid_file(
                file_path, file_size, download_failed
            ):  # download failed
                time.sleep(3)
                download_failed = False
                try:
                    with open(file_path, "wb") as tmp_file:
                        for chunk in open_file(prefix, instance_id):
                            tmp_file.write(chunk)
                except Exception as e:
                    download_failed = True
                    exception = e

                if is_unvalid_file(
                    file_path, file_size, download_failed
                ):  # download failed again
                    rm_file(file_path)
                    if exception is not None:
                        raise exception
                    else:
                        raise DownloadFromStorageFailedException

    return file_path


def is_unvalid_file(file_path, file_size=None, download_failed=False):
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
