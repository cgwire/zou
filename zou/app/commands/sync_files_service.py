"""
File synchronization (previews, thumbnails, attachments) from another
Kitsu instance. Files are downloaded to a temporary path first and cleaned
up on failure so a partial download never lands in the store.
"""

import os
import time
import traceback

import gazu

from flask_fs.backends.local import LocalBackend
from http.client import responses as http_responses
from threading import RLock
from multiprocessing.pool import ThreadPool as Pool

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.organisation import Organisation
from zou.app.models.person import Person
from zou.app.models.preview_background_file import PreviewBackgroundFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task

from zou.app.services import (
    preview_file_states_service,
    projects_service,
)
from zou.app.stores import file_store
from zou.app.utils import fs
from zou.app import config
from zou.app.commands.sync_service import (
    _add_time_window,
    _fetch_events,
    event_name_model_map,
    forward_local_event,
    logger,
)

lock = RLock()

preview_folder = config.PREVIEW_FOLDER
local_picture = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "pictures")}
)
local_movie = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "movies")}
)
local_file = LocalBackend(
    "local", {"root": os.path.join(preview_folder, "files")}
)

thumbnail_events = [
    "organisation",
    "person",
    "project",
]

file_events = [
    "preview-background-file:add-file",
    "preview-file:add-file",
    "organisation:set-thumbnail",
    "person:set-thumbnail",
    "project:set-thumbnail",
]


def run_last_events_files(minutes=0, limit=50):
    """
    Retrieve last events from source instance and import related data and
    action.
    """
    path = f"events/last?only_files=true&limit={limit}"
    if minutes > 0:
        path = _add_time_window(path, minutes)
    events = _fetch_events(path, limit, paginate=minutes > 0)
    events.reverse()
    for event in events:
        event_name = event["name"].split(":")[0]
        if event_name == "preview-file":
            preview_file = PreviewFile.get(event["data"]["preview_file_id"])
            if preview_file is not None:
                download_preview_from_another_instance(preview_file)
        elif event_name in ["preview-background-file"]:
            preview_background_file = PreviewBackgroundFile.get(
                event["data"]["preview_background_file_id"]
            )
            if preview_background_file is not None:
                download_preview_background_from_another_instance(
                    preview_background_file
                )
        else:
            download_thumbnail_from_another_instance(
                event_name, event["data"][f"{event_name}_id"]
            )


def add_file_listeners(event_client):
    """
    Add new preview event listener.
    """
    gazu.events.add_listener(
        event_client, "preview-file:add-file", retrieve_preview_file
    )
    gazu.events.add_listener(
        event_client,
        "preview-background-file:add-file",
        retrieve_preview_background_file,
    )
    for model_name in thumbnail_events:
        gazu.events.add_listener(
            event_client,
            f"{model_name}:set-thumbnail",
            get_retrieve_thumbnail(model_name),
        )


def retrieve_preview_file(data):
    """
    Event handler: download the preview file another instance just added,
    then forward the event locally. Events flagged sync are skipped, they
    are the ones this instance emitted itself.
    """
    if data.get("sync", False):
        return
    try:
        preview_file_id = data["preview_file_id"]
        preview_file = PreviewFile.get(preview_file_id)
        download_preview_from_another_instance(preview_file)
        forward_local_event("preview-file:add-file", data)
        logger.info(f"Preview file and related downloaded: {preview_file_id}")
    except gazu.exception.RouteNotFoundException as e:
        logger.error(f"Route not found: {e}")
        logger.error(f"Fail to download preview file: {preview_file_id}")


def retrieve_preview_background_file(data):
    """
    Event handler: download the preview background file another instance
    just added, then forward the event locally.
    """
    if data.get("sync", False):
        return
    try:
        preview_background_file_id = data["preview_background_file_id"]
        preview_background_file = PreviewBackgroundFile.get(
            preview_background_file_id
        )
        download_preview_background_from_another_instance(
            preview_background_file
        )
        forward_local_event("preview-background-file:add-file", data)
        logger.info(
            f"Preview background file and related downloaded: {preview_background_file_id}"
        )
    except gazu.exception.RouteNotFoundException as e:
        logger.error(f"Route not found: {e}")
        logger.error(
            f"Fail to download preview background file: {preview_background_file_id}"
        )


def get_retrieve_thumbnail(model_name):
    """
    Build the event handler downloading the thumbnail of given model from
    the other instance. One handler per model, hence the closure.
    """

    def retrieve_thumbnail(data):
        if data.get("sync", False):
            return
        try:
            # The thumbnail of a person is stored under the person id: the
            # <model>:set-thumbnail events carry that id, never the id of a
            # preview file.
            instance_id = data[f"{model_name}_id"]
            download_thumbnail_from_another_instance(model_name, instance_id)
            forward_local_event(f"{model_name}:set-thumbnail", data)
            logger.info(f"Thumbnail downloaded: {model_name} {instance_id}")
        except gazu.exception.RouteNotFoundException as e:
            logger.error(f"Route not found: {e}")
            logger.error(
                f"Fail to download thumbnail: {model_name} {instance_id}"
            )

    return retrieve_thumbnail


def download_entity_thumbnails_from_storage():
    """
    Download all thumbnail files for non preview entries from object storage
    and store them locally.
    """
    for project in Project.query.all():
        download_entity_thumbnail(project)
    for organisation in Organisation.query.all():
        download_entity_thumbnail(organisation)
    for person in Person.query.all():
        download_entity_thumbnail(person)


def download_preview_files_from_storage():
    """
    Download all thumbnail and original files for preview entries from object
    storage and store them locally.
    """
    for preview_file in PreviewFile.query.all():
        download_preview(preview_file)


def download_entity_thumbnail(entity):
    """
    Download thumbnail file for given entity from object storage and store it
    locally.
    """
    local = LocalBackend(
        "local", {"root": os.path.join(preview_folder, "pictures")}
    )

    file_path = local.path("thumbnails-" + str(entity.id))
    dirname = os.path.dirname(file_path)
    if entity.has_avatar:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(file_path, "wb") as tmp_file:
            for chunk in file_store.open_picture("thumbnails", str(entity.id)):
                tmp_file.write(chunk)


def download_file(file_path, prefix, dl_func, preview_file_id):
    """
    Download preview file for given preview from object storage and store it
    locally.
    """
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # Written through a temporary file: a partial download would be
    # mistaken for a valid one on the next sync run. Logged rather than
    # raised, one file must not fail the whole sync.
    exception = fs.download_to_file(
        file_path, dl_func, prefix, preview_file_id
    )
    if exception is None:
        logger.info(f"{file_path} downloaded")
    else:
        logger.error(
            f"Failed to download {prefix} {preview_file_id}",
            exc_info=exception,
        )


def download_preview(preview_file):
    """
    Download all files link to preview file entry: orginal file and variants.
    """
    logger.info(
        f"download preview {preview_file.id} ({preview_file.extension})"
    )
    is_movie = preview_file.extension == "mp4"
    is_picture = preview_file.extension == "png"
    is_file = not is_movie and not is_picture

    preview_file_id = str(preview_file.id)
    file_key = f"previews-{preview_file_id}"
    if is_file:
        file_path = local_file.path(file_key)
        dl_func = file_store.open_file
    elif is_movie:
        file_path = local_movie.path(file_key)
        dl_func = file_store.open_movie
    else:
        file_path = local_picture.path(file_key)
        dl_func = file_store.open_picture

    if is_movie or is_picture:
        for prefix in ["thumbnails", "thumbnails-square", "original"]:
            pic_dl_func = file_store.open_picture
            pic_file_path = local_picture.path(f"{prefix}-{preview_file.id!s}")
            download_file(pic_file_path, prefix, pic_dl_func, preview_file_id)

    download_file(file_path, "previews", dl_func, preview_file_id)


def write_multithread_dict_errors(dict_errors, prefix, id, error):
    """
    Write a value in a dictionnary in a thread safe way.
    """
    with lock:
        if prefix not in dict_errors:
            dict_errors[prefix] = {}
        dict_errors[prefix][id] = error


def download_files_from_another_instance(
    project=None,
    multithreaded=False,
    number_workers=30,
    number_attemps=3,
    force_resync=False,
    include_broken=True,
    include_missing=True,
):
    """
    Download all files from source instance.
    """
    pool = None
    if multithreaded:
        pool = Pool(number_workers)

    dict_errors = {}

    download_thumbnails_from_another_instance(
        "person",
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
    )
    download_thumbnails_from_another_instance(
        "organisation",
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
    )
    download_thumbnails_from_another_instance(
        "project",
        project=project,
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
    )
    download_preview_files_from_another_instance(
        project=project,
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
        include_broken=include_broken,
        include_missing=include_missing,
    )
    download_preview_background_files_from_another_instance(
        project=project,
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
    )
    download_attachment_files_from_another_instance(
        project=project,
        pool=pool,
        number_attemps=number_attemps,
        force=force_resync,
        dict_errors=dict_errors,
    )

    if pool is not None:
        pool.close()
        pool.join()

    return dict_errors


def download_thumbnails_from_another_instance(
    model_name,
    project=None,
    pool=None,
    number_attemps=3,
    force=False,
    dict_errors=None,
):
    """
    Download all thumbnails from source instance for given model.
    """
    if dict_errors is None:
        dict_errors = {}
    model = event_name_model_map[model_name]

    if project is None:
        instances = model.query
    else:
        project = gazu.project.get_project_by_name(project)
        instances = model.query.filter_by(id=project.get("id"))

    number_of_thumbnails = instances.count()
    logger.info(
        f"Downloading {model_name} thumbnails ({number_of_thumbnails})..."
    )
    for i, instance in enumerate(instances):
        if instance.has_avatar:
            args = (
                model_name,
                instance.id,
                number_attemps,
                i + 1,
                number_of_thumbnails,
                force,
                dict_errors,
            )
            if pool is None:
                download_thumbnail_from_another_instance(*args)
            else:
                pool.apply_async(
                    download_thumbnail_from_another_instance,
                    args,
                )


def download_thumbnail_from_another_instance(
    model_name,
    model_id,
    number_attemps=3,
    index=0,
    total=0,
    force=False,
    dict_errors=None,
):
    """
    Download into the local storage the thumbnail for a given model instance.
    """
    if dict_errors is None:
        dict_errors = {}
    file_path = f"/tmp/thumbnails-{model_id}.png"
    path = f"/pictures/thumbnails/{model_name}s/{model_id}.png"
    download_file_from_another_instance(
        path,
        file_path,
        file_store.exists_picture,
        file_store.add_picture,
        "thumbnails",
        model_id,
        number_attemps,
        force,
        dict_errors,
    )
    logger.info(
        f"{index:0{len(str(total))}}/{total} Thumbnail {model_name} file {model_id} processed."
    )


def download_preview_files_from_another_instance(
    project=None,
    pool=None,
    number_attemps=3,
    force=False,
    dict_errors=None,
    include_broken=True,
    include_missing=True,
):
    """
    Download all preview files and related (thumbnails and low def included).
    """
    if dict_errors is None:
        dict_errors = {}
    if project:
        project_dict = gazu.project.get_project_by_name(project)
        preview_files = PreviewFile.query.join(Task).filter(
            Task.project_id == project_dict["id"]
        )
    else:
        preview_files = PreviewFile.query

    excluded_statuses = []
    if not include_broken:
        excluded_statuses.append("broken")
    if not include_missing:
        excluded_statuses.append("missing")
    if excluded_statuses:
        preview_files = preview_files.filter(
            PreviewFile.status.notin_(excluded_statuses)
        )

    number_of_preview_files = preview_files.count()
    logger.info(f"Downloading preview files ({number_of_preview_files})...")
    for i, preview_file in enumerate(preview_files):
        args = (
            preview_file,
            number_attemps,
            force,
            i + 1,
            number_of_preview_files,
            dict_errors,
        )
        if pool is None:
            download_preview_from_another_instance(*args)
        else:
            pool.apply_async(
                download_preview_from_another_instance,
                args,
            )


def download_preview_background_files_from_another_instance(
    project=None, pool=None, number_attemps=3, force=False, dict_errors=None
):
    """
    Download all preview background files and related.
    """
    if dict_errors is None:
        dict_errors = {}
    if project:
        project_dict = gazu.project.get_project_by_name(project)
        project = projects_service.get_project_raw(project_dict["id"])
        preview_background_files = project.preview_background_files
        number_of_preview_background_files = len(preview_background_files)
    else:
        preview_background_files = PreviewBackgroundFile.query
        number_of_preview_background_files = preview_background_files.count()
    logger.info(
        f"Downloading preview background files ({number_of_preview_background_files})..."
    )
    for i, preview_background_file in enumerate(preview_background_files):
        args = (
            preview_background_file,
            number_attemps,
            force,
            i + 1,
            number_of_preview_background_files,
            dict_errors,
        )
        if pool is None:
            download_preview_background_from_another_instance(*args)
        else:
            pool.apply_async(
                download_preview_background_from_another_instance, args
            )


def download_preview_from_another_instance(
    preview_file,
    number_attemps=3,
    force=False,
    index=0,
    total=0,
    dict_errors=None,
):
    """
    Download all files link to preview file entry: orginal file and variants.
    """
    if dict_errors is None:
        dict_errors = {}
    is_movie = preview_file.extension == "mp4"
    is_picture = preview_file.extension == "png"
    is_file = not is_movie and not is_picture
    preview_file_id = str(preview_file.id)

    file_tree = {}
    if is_movie:
        file_tree[f"/movies/originals/preview-files/{preview_file_id}.mp4"] = {
            "prefix": "previews",
            "exist_func": file_store.exists_movie,
            "save_func": file_store.add_movie,
        }
        file_tree[f"/movies/low/preview-files/{preview_file_id}.mp4"] = {
            "prefix": "lowdef",
            "exist_func": file_store.exists_movie,
            "save_func": file_store.add_movie,
        }
        if config.SYNC_SOURCE_MOVIE_FILES:
            # An instance that skips the normalization stores the source
            # only, and its preview routes fall back on it. Replicating
            # `previews` alone would leave nothing to serve here.
            file_tree[
                f"/movies/source/preview-files/{preview_file_id}.mp4"
            ] = {
                "prefix": "source",
                "exist_func": file_store.exists_movie,
                "save_func": file_store.add_movie,
            }
        file_tree[f"/movies/tiles/preview-files/{preview_file_id}.png"] = {
            "prefix": "tiles",
            "exist_func": file_store.exists_picture,
            "save_func": file_store.add_picture,
        }
    if not is_file:
        file_tree[
            f"/pictures/thumbnails/preview-files/{preview_file_id}.png"
        ] = {
            "prefix": "thumbnails",
            "exist_func": file_store.exists_picture,
            "save_func": file_store.add_picture,
        }
        file_tree[
            f"/pictures/thumbnails-square/preview-files/{preview_file_id}.png"
        ] = {
            "prefix": "thumbnails-square",
            "exist_func": file_store.exists_picture,
            "save_func": file_store.add_picture,
        }
        file_tree[
            f"/pictures/previews/preview-files/{preview_file_id}.png"
        ] = {
            "prefix": "previews",
            "exist_func": file_store.exists_picture,
            "save_func": file_store.add_picture,
        }
        file_tree[
            f"/pictures/originals/preview-files/{preview_file_id}.png"
        ] = {
            "prefix": "original",
            "exist_func": file_store.exists_picture,
            "save_func": file_store.add_picture,
        }
    else:
        file_tree[
            f"/pictures/originals/preview-files/{preview_file_id}.{preview_file.extension}"
        ] = {
            "prefix": "previews",
            "exist_func": file_store.exists_file,
            "save_func": file_store.add_file,
        }

    for path, prefix_func in file_tree.items():
        file_path = f"/tmp/{prefix_func['prefix']}-{preview_file_id}.{preview_file.extension}"
        download_file_from_another_instance(
            path,
            file_path,
            prefix_func["exist_func"],
            prefix_func["save_func"],
            prefix_func["prefix"],
            preview_file_id,
            number_attemps,
            force,
            dict_errors,
        )

    _record_synced_preview_states(preview_file_id, preview_file.extension)

    logger.info(
        f"{index:0{len(str(total))}}/{total} Preview file {preview_file_id} processed."
    )


def _record_synced_preview_states(preview_file_id, extension):
    """
    Probe the storage for the expected files of a preview file just
    synced from another instance and record their states.

    download_preview_from_another_instance runs in a ThreadPool worker
    when the sync is multithreaded, which carries no Flask app context:
    it brings its own, the same way
    files_service.probe_and_record_movie_prefixes does.
    """
    from flask import has_app_context
    from zou.app import app

    def run():
        preview_file_states_service.record_file_states(
            preview_file_id,
            preview_file_states_service.probe_file_states(
                preview_file_id, extension
            ),
        )

    if has_app_context():
        run()
    else:
        with app.app_context():
            run()


def download_preview_background_from_another_instance(
    preview_background,
    number_attemps=3,
    force=False,
    index=0,
    total=0,
    dict_errors=None,
):
    """
    Download all files link to preview background file entry.
    """
    if dict_errors is None:
        dict_errors = {}
    preview_background_file_id = str(preview_background.id)
    for prefix in [
        "thumbnails",
        "preview-backgrounds",
    ]:
        extension = (
            "png" if prefix == "thumbnails" else preview_background.extension
        )
        if prefix == "preview-backgrounds":
            path = f"/pictures/preview-background-files/{preview_background_file_id}.{extension}"
        elif prefix == "thumbnails":
            path = f"/pictures/thumbnails/preview-background-files/{preview_background_file_id}.png"

        file_path = f"/tmp/{prefix}-{preview_background_file_id}.{extension}"
        download_file_from_another_instance(
            path,
            file_path,
            file_store.exists_picture,
            file_store.add_picture,
            prefix,
            preview_background_file_id,
            number_attemps,
            force,
            dict_errors,
        )
    logger.info(
        f"{index:0{len(str(total))}}/{total} Preview background file {preview_background_file_id} processed."
    )


def download_attachment_files_from_another_instance(
    project=None, pool=None, number_attemps=3, force=False, dict_errors=None
):
    """
    Download every attachment file of a project from the other instance,
    in parallel over the given pool.
    """
    if dict_errors is None:
        dict_errors = {}
    if project:
        project_dict = gazu.project.get_project_by_name(project)
        attachment_files = (
            AttachmentFile.query.join(Comment)
            .join(Task, Comment.object_id == Task.id)
            .filter(Task.project_id == project_dict["id"])
        )
    else:
        attachment_files = AttachmentFile.query

    number_of_attachment_files = attachment_files.count()
    logger.info(
        f"Downloading attachment files ({number_of_attachment_files})..."
    )
    for i, attachment_file in enumerate(attachment_files):
        args = (
            attachment_file.present(),
            number_attemps,
            i + 1,
            number_of_attachment_files,
            force,
            dict_errors,
        )
        if pool is None:
            download_attachment_file_from_another_instance(*args)
        else:
            pool.apply_async(
                download_attachment_file_from_another_instance,
                args,
            )


def download_attachment_file_from_another_instance(
    attachment_file,
    number_attemps=3,
    index=0,
    total=0,
    force=False,
    dict_errors=None,
):
    """
    Download one attachment file from the other instance, retrying up to
    number_attemps times.
    """
    if dict_errors is None:
        dict_errors = {}
    attachment_file_id = attachment_file["id"]
    extension = attachment_file["extension"]
    path = f"/data/attachment-files/{attachment_file_id}/file/{attachment_file['name']}"
    file_path = f"/tmp/{attachment_file_id}.{extension}"
    download_file_from_another_instance(
        path,
        file_path,
        file_store.exists_file,
        file_store.add_file,
        "attachments",
        attachment_file_id,
        number_attemps,
        force,
        dict_errors,
    )
    logger.info(
        f"{index:0{len(str(total))}}/{total} Attachment file {attachment_file_id} processed."
    )


def download_file_from_another_instance(
    path,
    file_path,
    exist_func,
    save_func,
    prefix,
    id,
    number_attemps=3,
    force=False,
    dict_errors=None,
):
    """
    Download one stored file from the other instance and save it locally.
    Skips a file already present unless force is set, and records the
    failures in dict_errors rather than raising.
    """
    if dict_errors is None:
        dict_errors = {}
    from zou.app import app

    with app.app_context():
        if force or not exist_func(prefix, id):
            for attempts_count in range(0, number_attemps):
                if attempts_count > 0:
                    time.sleep(0.5)
                try:
                    # processing_timeout=0: a sync has no reason to wait
                    # for a remote file still being built, unlike an
                    # interactive client. A preview still "processing" on
                    # the source instance should fail this attempt right
                    # away, not eat into this call's own retry budget.
                    response = gazu.client.download(
                        path, file_path, processing_timeout=0
                    )
                    if response.status_code != 200:
                        e = gazu.exception.DownloadFileException(
                            f"{response.status_code} {http_responses[response.status_code]}."
                        )
                        e.status_code = response.status_code
                        raise e
                except Exception as e:
                    if attempts_count + 1 == number_attemps:
                        if isinstance(e, gazu.exception.DownloadFileException):
                            error = f"Download failed ({path}):\n{e}"
                        else:
                            error = f"Download failed ({path}):\n{traceback.format_exc()}"
                        logger.error(error)

                        if (
                            not isinstance(
                                e, gazu.exception.DownloadFileException
                            )
                            or e.status_code != 404
                        ):
                            write_multithread_dict_errors(
                                dict_errors,
                                prefix,
                                id,
                                error,
                            )
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    continue
                try:
                    save_func(prefix, id, file_path)
                    break
                except Exception:
                    if attempts_count + 1 == number_attemps:
                        error = f"Upload failed ({path}):\n{traceback.format_exc()}"
                        write_multithread_dict_errors(
                            dict_errors,
                            prefix,
                            id,
                            error,
                        )
                finally:
                    os.remove(file_path)
    return path, file_path
