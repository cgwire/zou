import datetime
import gzip
import os

from sh import pg_dump

from zou.app.models.organisation import Organisation
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project

from zou.app.stores import file_store
from zou.app.utils import date_helpers

from flask_fs.backends.local import LocalBackend


preview_folder = os.getenv("PREVIEW_FOLDER", "/opt/zou/previews")
local_picture = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "pictures")}
)
local_movie = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "movies")}
)
local_file = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "files")}
)


def generate_db_backup(host, port, user, password, database):
    """
    Generate a Postgres dump file from the database.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = "%s-zou-db-backup.dump" % now
    with gzip.open(filename, "wb") as archive:
        pg_dump(
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            database,
            _out=archive,
            _env={"PGPASSWORD": password},
        )
    return filename


def store_db_backup(filename):
    """
    Store given file located in the same directory, inside the files bucket
    using the `dbbackup` prefix.
    """
    from zou.app import app

    with app.app_context():
        file_store.add_file("dbbackup", filename, filename)


def upload_preview_files_to_storage(days=None):
    """
    Upload all thumbnail and original files for preview entries to object
    storage.
    """
    query = PreviewFile.query
    if days is not None:
        limit_date = date_helpers.get_date_from_now(int(days))
        query = query.filter(PreviewFile.updated_at >= limit_date)

    for preview_file in query.all():
        upload_preview(preview_file)


def upload_entity_thumbnail(entity):
    """
    Upload thumbnail file for given entity to object storage.
    """
    preview_folder = os.getenv("PREVIEW_FOLDER", "/opt/zou/previews")
    local = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "pictures")}
    )

    file_path = local.path("thumbnails-" + str(entity.id))
    if entity.has_avatar:
        file_store.add_picture("thumbnails", str(entity.id), file_path)
        print("%s uploaded" % file_path)


def upload_preview(preview_file):
    """
    Upload all files link to preview file entry: orginal file and variants.
    """
    print("upload preview %s (%s)" % (preview_file.id, preview_file.extension))

    preview_folder = os.getenv("PREVIEW_FOLDER", "/opt/zou/previews")
    local_picture = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "pictures")}
    )
    local_movie = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "movies")}
    )
    local_file = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "files")}
    )

    is_movie = preview_file.extension == "mp4"
    is_picture = preview_file.extension == "png"
    is_file = not is_movie and not is_picture

    preview_file_id = str(preview_file.id)
    file_key = "previews-%s" % preview_file_id
    if is_picture:
        file_path = local_picture.path(file_key)
        ul_func = file_store.add_picture
        exists_func = file_store.exists_picture
    elif is_movie:
        file_path = local_movie.path(file_key)
        ul_func = file_store.add_movie
        exists_func = file_store.exists_movie
    elif is_file:
        file_path = local_file.path(file_key)
        ul_func = file_store.add_file
        exists_func = file_store.exists_file

    if is_movie or is_picture:
        for prefix in ["thumbnails", "thumbnails-square", "original"]:
            pic_file_path = local_picture.path(
                "%s-%s" % (prefix, str(preview_file.id))
            )
            if os.path.exists(pic_file_path) and not file_store.exists_picture(
                prefix, preview_file_id
            ):
                file_store.add_picture(prefix, preview_file_id, pic_file_path)

    prefix = "previews"
    if os.path.exists(file_path) and not exists_func(prefix, preview_file_id):
        ul_func(prefix, preview_file_id, file_path)
    print("%s uploaded" % file_path)


def upload_entity_thumbnails_to_storage(days=None):
    """
    Upload all thumbnail files for non preview entries to object storage.
    """
    upload_entity_thumbnails(Project, days)
    upload_entity_thumbnails(Organisation, days)
    upload_entity_thumbnails(Person, days)


def upload_entity_thumbnails(model, days=None):
    query = model.query
    if days is not None:
        limit_date = date_helpers.get_date_from_now(int(days))
        query = query.filter(model.updated_at >= limit_date)

    for entity in query.all():
        upload_entity_thumbnail(entity)
