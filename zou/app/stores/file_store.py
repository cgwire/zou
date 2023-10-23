import os
import flask_fs

from zou.app import config

from flask_fs.backends.local import LocalBackend

pictures = None
movies = None
files = None


def path(self, filename):
    folder_one = filename.split("-")[0]
    file_name = "-".join(filename.split("-")[1:])
    folder_two = file_name[:3]
    folder_three = file_name[3:6]

    return os.path.join(
        self.root, folder_one, folder_two, folder_three, file_name
    )


LocalBackend.path = path


def configure_storages(app):
    global pictures, movies, files
    pictures = make_storage("pictures")
    movies = make_storage("movies")
    files = make_storage("files")

    flask_fs.init_app(app, *[pictures, movies, files])


def clear_bucket(bucket):
    for filename in bucket.list_files():
        if isinstance(bucket.backend, LocalBackend):
            folder_one, _, _, file_name = filename.split("/")
            bucket.delete(f"{folder_one}-{file_name}")
        else:
            bucket.delete(filename)


def make_key(prefix, id):
    return f"{prefix}-{id}"


def make_read_generator(bucket, key):
    read_stream = bucket.read_chunks(key)

    def read_generator(read_stream):
        for chunk in read_stream:
            yield chunk

    return read_generator(read_stream)


def make_storage(bucket):
    return flask_fs.Storage(
        "%s%s" % (config.FS_BUCKET_PREFIX, bucket),
        overwrite=True,
    )


def clear():
    clear_bucket(pictures)
    clear_bucket(movies)
    clear_bucket(files)


def add_picture(prefix, id, path):
    key = make_key(prefix, id)
    with open(path, "rb") as fd:
        return pictures.write(key, fd)


def get_picture(prefix, id):
    key = make_key(prefix, id)
    return pictures.read(key)


def open_picture(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(pictures, key)


def read_picture(prefix, id):
    key = make_key(prefix, id)
    return pictures.read(key)


def exists_picture(prefix, id):
    key = make_key(prefix, id)
    return pictures.exists(key)


def remove_picture(prefix, id):
    key = make_key(prefix, id)
    return pictures.delete(key)


def get_local_picture_path(prefix, id):
    return path(pictures, make_key(prefix, id))


def add_movie(prefix, id, path):
    key = make_key(prefix, id)
    with open(path, "rb") as fd:
        return movies.write(key, fd)


def get_movie(prefix, id):
    key = make_key(prefix, id)
    return movies.read(key)


def open_movie(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(movies, key)


def read_movie(prefix, id):
    key = make_key(prefix, id)
    return movies.read(key)


def exists_movie(prefix, id):
    key = make_key(prefix, id)
    return movies.exists(key)


def remove_movie(prefix, id):
    key = make_key(prefix, id)
    return movies.delete(key)


def get_local_movie_path(prefix, id):
    return path(movies, make_key(prefix, id))


def add_file(prefix, id, path):
    key = make_key(prefix, id)
    with open(path, "rb") as fd:
        return files.write(key, fd)


def get_file(prefix, id):
    key = make_key(prefix, id)
    return files.read(key)


def open_file(prefix, id):
    key = make_key(prefix, id)
    return make_read_generator(files, key)


def read_file(prefix, id):
    key = make_key(prefix, id)
    return files.read(key)


def exists_file(prefix, id):
    key = make_key(prefix, id)
    return files.exists(key)


def remove_file(prefix, id):
    key = make_key(prefix, id)
    return files.delete(key)


def get_local_file_path(prefix, id):
    return path(files, make_key(prefix, id))
