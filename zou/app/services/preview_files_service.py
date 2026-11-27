import logging
import os
import shutil
import time

import ffmpeg
import redis
import slugify
from rq import Queue, Retry, get_current_job
from rq.timeouts import BaseTimeoutException
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from zou.app import config
from zou.app.exceptions import (
    PreviewFileNotFoundException,
    PreviewProcessingFailedException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project, ProjectTaskTypeLink
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    deletion_service,
    entities_service,
    files_service,
    news_service,
    organisation_service,
    preview_file_states_service,
    projects_service,
    stored_files_service,
    task_types_service,
    tasks_service,
)
from zou.app.stores import (
    config_store,
    file_store,
    queue_store,
)
from zou.app.utils import (
    events,
    fields,
    fs,
    remote_job,
    thumbnail as thumbnail_utils,
)
from zou.utils import movie

logger = logging.getLogger(__name__)


REMOTE_NORMALIZE_VERSION = 2
# Seconds before each new attempt of a preview processing job if its
# upload to the object storage failed on authentication (Keystone down).
# During this time, the uploaded file waits in PENDING_UPLOADS_FOLDER,
# which the TMP_DIR cleanup skips, and the preview file stays
# "processing".
STORAGE_RETRY_INTERVALS = (60, 300, 900, 3600)
STORAGE_RETRIES_META_KEY = "storage_retries"
PENDING_UPLOADS_FOLDER = "pending-uploads"


def get_preview_file_dimensions(project, entity=None):
    """
    Return the dimensions set at entity level or project level, or the
    default dimensions if no dimensions are set. The entity resolution has
    priority over the project resolution. The default size is based on a
    height of 1080.
    """
    resolution = project["resolution"]
    entity_data = {}
    if entity is not None:
        entity_data = entity.get("data", {}) or {}
    entity_resolution = entity_data.get("resolution", None)
    width = None
    height = 1080

    if projects_service.is_valid_resolution(entity_resolution):
        resolution = entity_resolution

    try:
        if projects_service.is_valid_resolution(resolution):
            [width, height] = resolution.split("x")
            width = int(width)
            height = int(height)
        elif projects_service.is_valid_partial_resolution(resolution):
            [_, height] = resolution.split("x")
            width = None
            height = int(height)
    except (ValueError, TypeError):
        # Defensive fallback: a malformed resolution string must not
        # crash the normalization worker. Use the default 1080.
        from zou.app import app as current_app

        current_app.logger.warning(
            "Invalid resolution %r, falling back to default", resolution
        )
        width = None
        height = 1080

    return (width, height)


def get_preview_file_fps(project, entity=None):
    """
    Return the fps set at entity level, else at project level, else 25, as a
    string with three decimals.
    """
    fps = "25.00"
    if project.get("fps", None) is not None:
        fps = project["fps"].replace(",", ".")

    if entity is not None:
        entity_data = entity.get("data", {}) or {}
        if entity_data.get("fps", None):
            fps = str(entity_data["fps"]).replace(",", ".")

    return f"{float(fps):.3f}"


def get_project_from_preview_file(preview_file_id):
    """
    Return the project dict of the related preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)

    task = Task.get(preview_file.task_id)
    project = Project.get(task.project_id)
    return project.serialize()


def get_task_type_link_from_preview_file(preview_file_id):
    """
    Return the project task type link dict of the related preview file, or
    None if the task type is not linked to the project.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task = Task.get(preview_file.task_id)
    link = ProjectTaskTypeLink.get_by(
        project_id=task.project_id, task_type_id=task.task_type_id
    )
    return link.serialize() if link is not None else None


def get_entity_from_preview_file(preview_file_id):
    """
    Return the entity dict of the related preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task = Task.get(preview_file.task_id)
    entity = Entity.get(task.entity_id)
    return entity.serialize()


def update_preview_file(preview_file_id, data, silent=False):
    """
    Update the given preview file and notify the clients, unless silent is
    set.
    """
    # Job workers can get a temporary database error immediately after the
    # request that created the row committed. The retries are for this
    # case. A row that does not exist will not appear in six seconds.
    try:
        preview_file = files_service.get_preview_file_raw(preview_file_id)
    except OperationalError:
        try:
            time.sleep(1)
            preview_file = files_service.get_preview_file_raw(preview_file_id)
        except OperationalError:
            time.sleep(5)
            preview_file = files_service.get_preview_file_raw(preview_file_id)
    return update_preview_file_raw(preview_file, data, silent=silent)


TRIM_KEYS = ("handle_in", "handle_out")


def get_preview_file_trim(data):
    """
    Return the in/out handles stored in the data of a preview file. A handle
    that is not set is None.
    """
    data = data if isinstance(data, dict) else {}
    return {key: data.get(key) for key in TRIM_KEYS}


def update_preview_file_trim(preview_file_id, trim):
    """
    Set the in/out handles of the given preview file. A None value clears the
    handle. The extra previews of a revision keep their own trim in the data:
    the trim of the main preview stays on the shot.

    Keep the other keys of the data, as the other writers of this column do
    (the stored movie prefixes).
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    data = files_service.get_preview_file_data(preview_file)
    if trim:
        data = {
            key: value
            for key, value in {**data, **trim}.items()
            if key not in trim or value is not None
        }
        update_preview_file_raw(preview_file, {"data": data})
    return {"id": str(preview_file.id), **get_preview_file_trim(data)}


def update_preview_file_raw(preview_file, data, silent=False):
    """
    Do the same as update_preview_file, on an active record that is already
    loaded.
    """
    # Read the id while the instance is still live. On StaleDataError,
    # base.update() rolls the session back, which expires all attributes.
    # A read of preview_file.id after that loads the (now deleted) row
    # again and raises ObjectDeletedError, which hides the real error.
    preview_file_id = str(preview_file.id)
    try:
        preview_file.update(data)
    except StaleDataError:
        from zou.app import app as current_app

        current_app.logger.warning(
            f"Preview file {preview_file_id} was deleted during update"
        )
        raise PreviewFileNotFoundException(
            f"Preview file {preview_file_id} was deleted"
        )

    files_service.clear_preview_file_cache(preview_file_id)
    task = Task.get(preview_file.task_id)
    # The single news shows these fields of the preview files of its comment.
    if data.keys() & {"extension", "name", "position", "revision", "status"}:
        for comment in preview_file.comments:
            news_service.clear_comment_news_cache(comment.id, task.project_id)
    if not silent:
        event_data = {"preview_file_id": preview_file_id}
        # The clients wait for the status before they ask again for the
        # pictures that a job builds in the background. A metadata refresh
        # of a ready preview leaves out the status: the maintenance commands
        # refresh all previews, and each client would get each picture
        # again.
        if "status" in data or preview_file.status == "processing":
            event_data["status"] = preview_file.status
        events.emit(
            "preview-file:update",
            event_data,
            project_id=str(task.project_id),
        )
    return preview_file.serialize()


def set_preview_file_as_broken(preview_file_id):
    """
    Mark the given preview file as broken.
    """
    return update_preview_file(preview_file_id, {"status": "broken"})


def set_preview_file_as_missing(preview_file_id):
    """
    Mark a preview file as missing: its source binary is not in the storage
    anymore and the normalization cannot run again.
    """
    return update_preview_file(preview_file_id, {"status": "missing"})


def remove_temp_files(*paths):
    """
    Remove the temporary files of the movie processing. Ignore the files
    that are already removed.
    """
    for path in paths:
        if path is not None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def get_pending_upload_path(upload_path):
    """
    Return the path where an upload waits until the object storage is
    available again. The path is under TMP_DIR, thus a move to it is a
    rename.
    """
    return os.path.join(
        config.TMP_DIR, PENDING_UPLOADS_FOLDER, os.path.basename(upload_path)
    )


def _resolve_upload_path(upload_path):
    """
    Return the path of the upload. A job that is queued again after a
    storage failure keeps its arguments. If the upload was moved to the
    pending folder, find it there.
    """
    if upload_path is None or os.path.exists(upload_path):
        return upload_path
    pending_path = get_pending_upload_path(upload_path)
    if os.path.exists(pending_path):
        return pending_path
    return upload_path


def is_scheduler_running(job):
    """
    Return True if a worker started with --with-scheduler serves the queue
    of the job. A job queued again with a delay goes into the scheduled
    registry, and only the scheduler moves it back to the queue. The
    scheduler holds a lock in Redis while it runs. The lock expires shortly
    after the scheduler stops.
    """
    try:
        queue = Queue(job.origin, connection=job.connection)
        return queue.scheduler_pid is not None
    except redis.RedisError:
        return False


def _requeue_on_storage_failure(exc, upload_path):
    """
    If the job failed on the object storage authentication and attempts
    remain, keep the upload aside. Then return the Retry that queues the
    running job again. Else, return None and the caller fails as usual.
    Return None in these cases:
    - there is no job (inline processing),
    - the error is another error,
    - no attempts remain,
    - no scheduler can queue the job again after the delay.
    """
    job = get_current_job()
    if job is None or not fs.is_auth_failure(exc):
        return None
    attempt = job.meta.get(STORAGE_RETRIES_META_KEY, 0)
    if attempt >= len(STORAGE_RETRY_INTERVALS):
        return None
    if not is_scheduler_running(job):
        from zou.app import app as current_app

        current_app.logger.warning(
            "No RQ scheduler running (rq worker --with-scheduler): the "
            "job is not queued again after the object storage failure"
        )
        return None
    pending_path = get_pending_upload_path(upload_path)
    if upload_path != pending_path:
        os.makedirs(os.path.dirname(pending_path), exist_ok=True)
        os.replace(upload_path, pending_path)
    job.meta[STORAGE_RETRIES_META_KEY] = attempt + 1
    # The next attempt starts from the beginning: do not resume a Nomad
    # job that this job dispatched as if the source were stored.
    job.meta.pop(remote_job.NOMAD_JOB_ID_META_KEY, None)
    job.save_meta()
    # Retry.max counts all retries of the job, with the handovers.
    return Retry(
        max=(job.number_of_retries or 0) + 1,
        interval=STORAGE_RETRY_INTERVALS[attempt],
    )


def mark_broken_on_job_failure(
    job, connection, exc_type, exc_value, traceback
):
    """
    RQ failure callback for the movie normalization and picture variant
    jobs: mark the preview file as broken and remove its temporary file.
    Without it, a job stopped by a timeout or a dead worker leaves the
    preview file on "processing" forever.
    """
    from zou.app import app as current_app

    preview_file_id = job.args[0]
    uploaded_movie_path = job.args[1] if len(job.args) > 1 else None
    with current_app.app_context():
        current_app.logger.error(
            f"Preview processing job failed for preview file "
            f"{preview_file_id}: {exc_value}"
        )
        if uploaded_movie_path is not None:
            remove_temp_files(
                uploaded_movie_path,
                get_pending_upload_path(uploaded_movie_path),
            )
        try:
            set_preview_file_as_broken(preview_file_id)
        except PreviewFileNotFoundException:
            current_app.logger.warning(
                f"Preview file {preview_file_id} was deleted before its "
                f"failed job could mark it as broken"
            )


def dispatch_movie_processing(
    preview_file_id,
    uploaded_movie_path,
    normalize=True,
    add_source_to_file_store=True,
    no_job=False,
):
    """
    Run prepare_and_store_movie on the job queue if one is enabled. Else,
    run it in the calling thread. A raw store is fast enough to stay
    synchronous. But the remote worker blocks until Nomad is done, and it
    builds the thumbnails even without normalization: it never runs in a
    request thread.
    """
    needs_job = normalize or is_remote_normalization_enabled()
    if needs_job and config.ENABLE_JOB_QUEUE and not no_job:
        queue_store.job_queue.enqueue(
            prepare_and_store_movie,
            args=(
                preview_file_id,
                uploaded_movie_path,
                normalize,
                add_source_to_file_store,
            ),
            job_timeout=int(config.JOB_QUEUE_TIMEOUT),
            on_failure=mark_broken_on_job_failure,
        )
    else:
        prepare_and_store_movie(
            preview_file_id,
            uploaded_movie_path,
            normalize=normalize,
            add_source_to_file_store=add_source_to_file_store,
        )


def prepare_and_store_movie(
    preview_file_id,
    uploaded_movie_path,
    normalize=True,
    add_source_to_file_store=True,
):
    """
    Change an uploaded movie into a ready preview file:
    - keep the source if asked,
    - encode the preview versions (here or on the remote worker),
    - build the thumbnails and the tile,
    - record the metadata and the stored versions.
    If a step fails, mark the preview file as broken. The job timeout is
    raised again, thus rq records the failure. Always remove the temporary
    files. In a job, if the object storage authentication fails and attempts
    remain, return a Retry.
    """
    from zou.app import app as current_app

    uploaded_movie_path = _resolve_upload_path(uploaded_movie_path)
    temp_files = [uploaded_movie_path]
    with current_app.app_context():
        try:
            return _process_movie(
                preview_file_id,
                uploaded_movie_path,
                normalize,
                add_source_to_file_store,
                temp_files,
            )
        except PreviewFileNotFoundException:
            current_app.logger.warning(
                f"Preview file {preview_file_id} was deleted during processing"
            )
            return {"id": preview_file_id, "status": "broken"}
        except remote_job.NomadJobHandedOver:
            # The worker stops: the next worker resumes the job and reads the
            # upload again.
            temp_files.remove(uploaded_movie_path)
            raise
        except BaseTimeoutException:
            # rq raises its timeout inside the job. If this code catches
            # it, the job counts as successful and
            # mark_broken_on_job_failure never runs.
            raise
        except Exception as exc:
            retry = _requeue_on_storage_failure(exc, uploaded_movie_path)
            if retry is not None:
                current_app.logger.warning(
                    f"Object storage unavailable, movie processing of "
                    f"preview file {preview_file_id} queued again: {exc}"
                )
                temp_files.remove(uploaded_movie_path)
                return retry
            if isinstance(exc, ffmpeg.Error):
                current_app.logger.error(exc.stderr)
            current_app.logger.error(
                f"Movie processing failed for preview file {preview_file_id}",
                exc_info=1,
            )
            try:
                return set_preview_file_as_broken(preview_file_id)
            except PreviewFileNotFoundException:
                return {"id": preview_file_id, "status": "broken"}
        finally:
            remove_temp_files(*temp_files)


def dispatch_picture_processing(
    preview_file_id, original_picture_path, no_job=False
):
    """
    Build the picture variants on the job queue if one is enabled. Else,
    build them in the calling thread. Return True if the work was queued,
    thus the caller knows if the preview file is still processing.

    As in the movie pipeline, the job receives a local path: the workers run
    on the API host, or share TMP_DIR with it.
    """
    if config.ENABLE_JOB_QUEUE and not no_job:
        queue_store.job_queue.enqueue(
            prepare_and_store_picture,
            args=(preview_file_id, original_picture_path),
            job_timeout=int(config.JOB_QUEUE_TIMEOUT),
            on_failure=mark_broken_on_job_failure,
        )
        return True
    prepare_and_store_picture(preview_file_id, original_picture_path)
    return False


def prepare_and_store_picture(preview_file_id, original_picture_path):
    """
    Build the variants of an uploaded picture, store them and mark the
    preview file as ready. This runs from a job and from a request: it
    creates its own app context if there is none. If it fails, mark the
    preview file as broken and raise the error again.
    """
    from flask import has_app_context

    from zou.app import app

    original_picture_path = _resolve_upload_path(original_picture_path)

    def run():
        keep_original = False
        try:
            # Keep it if a failure occurs: a job queued again uploads it again.
            save_variants(
                preview_file_id, original_picture_path, remove_original=False
            )
            preview_file = update_preview_file(
                preview_file_id, {"status": "ready"}
            )
            tasks_service.update_preview_file_info(preview_file)
        except PreviewFileNotFoundException:
            # The preview file was deleted while the job waited: build nothing.
            app.logger.warning(
                f"Preview file {preview_file_id} was deleted before its "
                f"variants could be built"
            )
        except BaseTimeoutException:
            # rq raises its timeout inside the job. If this code catches
            # it, the job counts as successful and
            # mark_broken_on_job_failure never runs.
            raise
        except Exception as exc:
            retry = _requeue_on_storage_failure(exc, original_picture_path)
            if retry is not None:
                app.logger.warning(
                    f"Object storage unavailable, picture processing of "
                    f"preview file {preview_file_id} queued again: {exc}"
                )
                keep_original = True
                return retry
            # This covers the inline path (no job queue, or ?no_job=true).
            # The queued path uses on_failure=mark_broken_on_job_failure,
            # but that callback never runs for a call from the request
            # thread. Mark the file as broken here first, then raise
            # again: this keeps both paths consistent and does not change
            # the failure handling of rq (which is idempotent).
            app.logger.error(
                f"Picture processing failed for preview file {preview_file_id}",
                exc_info=1,
            )
            try:
                set_preview_file_as_broken(preview_file_id)
            except PreviewFileNotFoundException:
                pass
            raise
        finally:
            if not keep_original:
                remove_temp_files(original_picture_path)

    if has_app_context():
        return run()
    with app.app_context():
        return run()


def _process_movie(
    preview_file_id,
    uploaded_movie_path,
    normalize,
    add_source_to_file_store,
    temp_files,
):
    """
    Run the movie pipeline, one step after the other. Each temporary file
    that it makes goes into temp_files, and the caller removes them.
    """
    # A job that resumes after a handover already stored the source.
    if add_source_to_file_store and not remote_job.is_resumed():
        file_store.add_movie("source", preview_file_id, uploaded_movie_path)
    _record_original_metadata(preview_file_id, uploaded_movie_path)
    fps, width, height, bitrates = _get_encoding_parameters(preview_file_id)

    # SKIP_NORMALIZATION_FULL changes each upload into a raw store, as if
    # the client asked for normalize=false. SKIP_NORMALIZATION_HIGHDEF only
    # removes the 28M encoding: the low def version is still built and
    # becomes the only encoded movie.
    is_remote = is_remote_normalization_enabled()
    encode = normalize and not config.SKIP_NORMALIZATION_FULL
    skip_high_def = config.SKIP_NORMALIZATION_HIGHDEF

    if is_remote:
        movie_path = _encode_on_remote_worker(
            preview_file_id,
            uploaded_movie_path,
            fps,
            width,
            height,
            bitrates,
            encode,
            skip_high_def,
            temp_files,
        )
    elif encode:
        movie_path = _encode_locally(
            preview_file_id,
            uploaded_movie_path,
            fps,
            width,
            height,
            bitrates,
            skip_high_def,
            temp_files,
        )
    else:
        # The upload is the preview. It goes under `previews` only if it
        # was not already stored as the source: the movie routes use one
        # if the other is missing, thus a second copy is not useful.
        if not add_source_to_file_store:
            file_store.add_movie(
                "previews", preview_file_id, uploaded_movie_path
            )
        movie_path = uploaded_movie_path

    metadata = _read_movie_metadata(movie_path)
    remote_handles_thumbnails = is_remote and REMOTE_NORMALIZE_VERSION >= 2
    if not remote_handles_thumbnails:
        _build_thumbnails_and_tile(
            preview_file_id,
            movie_path,
            (metadata["width"], metadata["height"]),
            temp_files,
        )

    stored_movie_prefixes = _get_stored_movie_prefixes(
        preview_file_id,
        is_remote,
        encode,
        skip_high_def,
        add_source_to_file_store,
    )
    _record_movie_states(
        preview_file_id, stored_movie_prefixes, remote_handles_thumbnails
    )
    preview_file_raw = files_service.get_preview_file_raw(preview_file_id)
    preview_file = update_preview_file_raw(
        preview_file_raw,
        {
            "status": "ready",
            **metadata,
            "data": {
                **files_service.get_preview_file_data(preview_file_raw),
                files_service.MOVIE_PREFIXES_KEY: stored_movie_prefixes,
            },
        },
    )
    tasks_service.update_preview_file_info(preview_file)
    return preview_file


def _record_original_metadata(preview_file_id, uploaded_movie_path):
    """
    Keep the size and duration of the upload before the encoding. This is
    optional: a failure here must not stop the pipeline. The update is
    silent, thus the clients only get the final "ready" update.
    """
    from zou.app import app as current_app

    try:
        original_width, original_height = movie.get_movie_size(
            uploaded_movie_path
        )
        preview_file_raw = files_service.get_preview_file_raw(preview_file_id)
        update_preview_file_raw(
            preview_file_raw,
            {
                "data": {
                    **files_service.get_preview_file_data(preview_file_raw),
                    "original_width": original_width,
                    "original_height": original_height,
                    "original_duration": movie.get_movie_duration(
                        uploaded_movie_path
                    ),
                    "original_file_size": os.path.getsize(uploaded_movie_path),
                }
            },
            silent=True,
        )
    except PreviewFileNotFoundException:
        current_app.logger.warning(
            f"Preview file {preview_file_id} was deleted while capturing "
            f"original video metadata; skipping metadata capture"
        )
    except Exception:
        current_app.logger.warning(
            f"Failed to capture original video metadata for "
            f"{uploaded_movie_path}; continuing without it",
            exc_info=1,
        )


def _get_encoding_parameters(preview_file_id):
    """
    Return the fps, the resolution and the (highdef, lowdef) bitrates for
    the preview encoding. They come from the project, the entity or the task
    type link that overrides them. The job can start before the transaction
    of the upload is visible to it: one retry covers that. If the preview
    file is still missing after the retry, it was deleted while the job
    waited.
    """
    for attempt in range(2):
        try:
            project = get_project_from_preview_file(preview_file_id)
            entity = get_entity_from_preview_file(preview_file_id)
            task_type_link = get_task_type_link_from_preview_file(
                preview_file_id
            )
            break
        except PreviewFileNotFoundException:
            if attempt == 1:
                raise
            time.sleep(2)
    fps = get_preview_file_fps(project, entity)
    width, height = get_preview_file_dimensions(project, entity)
    bitrates = projects_service.get_movie_bitrates(project, task_type_link)
    return fps, width, height, bitrates


def _encode_locally(
    preview_file_id,
    uploaded_movie_path,
    fps,
    width,
    height,
    bitrates,
    skip_high_def,
    temp_files,
):
    """
    Encode the preview versions with ffmpeg and store them. Return the movie
    that the metadata and the thumbnails are read from: the high def movie,
    or the low def movie if the high def is skipped.
    """
    highdef_bitrate, lowdef_bitrate = bitrates
    high_def_path, low_def_path, err = movie.normalize_movie(
        uploaded_movie_path,
        fps=fps,
        width=width,
        height=height,
        skip_high_def=skip_high_def,
        highdef_bitrate=highdef_bitrate,
        lowdef_bitrate=lowdef_bitrate,
        preset=config.MOVIE_ENCODING_PRESET,
        vbv_bufsize_factor=config.MOVIE_VBV_BUFSIZE_FACTOR,
    )
    temp_files.extend(path for path in (high_def_path, low_def_path) if path)
    if err:
        raise PreviewProcessingFailedException(err)
    if high_def_path is not None:
        file_store.add_movie("previews", preview_file_id, high_def_path)
    file_store.add_movie("lowdef", preview_file_id, low_def_path)
    return high_def_path or low_def_path


def _encode_on_remote_worker(
    preview_file_id,
    uploaded_movie_path,
    fps,
    width,
    height,
    bitrates,
    encode,
    skip_high_def,
    temp_files,
):
    """
    Give the movie to the remote worker. The worker reads the source from
    the storage, encodes it and builds the thumbnails and the tile. It runs
    even if nothing must be encoded. Return the movie that the metadata is
    read from: the encoded version fetched from the storage, or the upload
    itself if nothing was encoded.
    """
    from zou.app import app as current_app

    _record_remote_normalize_writes(preview_file_id, encode, skip_high_def)
    result = _run_remote_normalize_movie(
        current_app,
        preview_file_id,
        fps,
        width,
        height,
        bitrates=bitrates,
        skip_high_def=skip_high_def,
        skip_normalization=not encode,
    )
    if result is not True:
        raise PreviewProcessingFailedException(result)
    if not encode:
        return uploaded_movie_path
    prefix = "lowdef" if skip_high_def else "previews"
    # The fetch writes to the cache path of the movie routes. A copy of an
    # earlier encoding can already be there (the movie was played on this
    # host, then normalized again). That copy would be read instead of the
    # new one: remove it first. The new copy does not stay either: the
    # worker can be a host that is not a web host, and nothing removes the
    # files of that cache.
    fs.rm_file(fs.get_cache_file_path(config, prefix, preview_file_id, "mp4"))
    movie_path = fs.get_file_path_and_file(
        config,
        file_store.get_local_movie_path,
        file_store.open_movie,
        prefix,
        preview_file_id,
        "mp4",
    )
    if config.FS_BACKEND != "local":
        temp_files.append(movie_path)
    return movie_path


def _record_remote_normalize_writes(preview_file_id, encode, skip_high_def):
    """
    Register the files that the remote worker can store, before it runs.
    Thus the objects that a failed job leaves are also known. The tile is
    included: its build can fail without a job failure, and a row without
    its object causes no problem.
    """
    written = [
        ("pictures", prefix, preview_file_id)
        for prefix in ["thumbnails", "thumbnails-square", "previews", "tiles"]
    ]
    if encode:
        written.append(("movies", "lowdef", preview_file_id))
        if not skip_high_def:
            written.append(("movies", "previews", preview_file_id))
    stored_files_service.record_remote_writes(written)


def _read_movie_metadata(movie_path):
    """
    Return the fields recorded on the preview file when it is ready.
    """
    width, height = movie.get_movie_size(movie_path)
    return {
        "width": width,
        "height": height,
        "file_size": os.path.getsize(movie_path),
        "duration": movie.get_movie_duration(movie_path),
    }


def _build_thumbnails_and_tile(preview_file_id, movie_path, size, temp_files):
    """
    Build the picture variants and the tile mosaic from the movie and store
    them. If the tile is missing, log it: it is not fatal.
    """
    from zou.app import app as current_app

    original_picture_path = movie.generate_thumbnail(movie_path)
    temp_files.append(original_picture_path)
    thumbnail_utils.turn_into_thumbnail(original_picture_path, size)
    save_variants(preview_file_id, original_picture_path)
    current_app.logger.info(f"thumbnail created {original_picture_path}")

    try:
        tile_path = movie.generate_tile(movie_path)
        store_tile(preview_file_id, tile_path)
        # The tile is stored. A failure to remove the local temporary
        # copy is not a generation failure and must not undo the
        # "ok" that was recorded above.
        try:
            os.remove(tile_path)
        except OSError:
            pass
        current_app.logger.info(f"tile created {tile_path}")
    except Exception:
        preview_file_states_service.record_file_state(
            preview_file_id,
            "pictures",
            "tiles",
            preview_file_states_service.FAILED,
        )
        current_app.logger.error("Failed to create tile", exc_info=1)


def _get_stored_movie_prefixes(
    preview_file_id, is_remote, encode, skip_high_def, add_source_to_file_store
):
    """
    Return the storage prefixes that hold the movie. They are recorded on
    the preview file, thus the movie routes do not have to probe the storage
    again to find them. Locally, the flags give them: the encoded versions,
    or the upload itself under `previews` if it was stored raw and not
    already kept as the source. A remote job does not give this data: a
    runner older than skip_high_def still uploads both encoded versions,
    thus the storage is probed once instead.
    """
    if is_remote:
        prefixes = files_service.probe_movie_prefixes(preview_file_id)
    elif encode:
        prefixes = ["lowdef"] if skip_high_def else ["previews", "lowdef"]
    elif add_source_to_file_store:
        prefixes = []
    else:
        prefixes = ["previews"]
    if add_source_to_file_store and "source" not in prefixes:
        prefixes.insert(0, "source")
    return prefixes


def _record_movie_states(
    preview_file_id, stored_movie_prefixes, remote_handles_thumbnails
):
    """
    Record the stored movie versions. If a remote job built them, also
    record the pictures that it wrote: a picture that it had to write and
    did not write is failed. A local build records its pictures when it
    stores them. A version that was not produced is not recorded as missing:
    another writer can still bring it, and only a read confirms an absence.
    """
    states = {
        ("movies", prefix): preview_file_states_service.OK
        for prefix in stored_movie_prefixes
    }
    if remote_handles_thumbnails:
        pictures = [
            key
            for key in preview_file_states_service.MOVIE_FILES
            if key[0] == "pictures"
        ]
        probed = preview_file_states_service.probe_file_states(
            preview_file_id, "mp4", files=pictures
        )
        states.update(
            preview_file_states_service.fail_missing(probed, pictures)
        )
    preview_file_states_service.record_file_states(preview_file_id, states)


def is_remote_normalization_enabled():
    """
    Return True if the movie processing runs on a remote worker. This occurs
    if the job queue is set to remote and a Nomad job name is configured.
    """
    return (
        config.ENABLE_JOB_QUEUE_REMOTE
        and len(config_store.get_nomad_normalize_job()) > 0
    )


def _run_remote_normalize_movie(
    app,
    preview_file_id,
    fps,
    width,
    height,
    bitrates=None,
    skip_high_def=False,
    skip_normalization=False,
):
    """
    Give the movie processing to a remote worker and wait for it. The worker
    also builds the thumbnails and the tile, thus it is dispatched even if
    no encoding is necessary.
    """
    params = {
        "version": str(REMOTE_NORMALIZE_VERSION),
        "preview_file_id": preview_file_id,
        "width": width,
        "height": height,
        "fps": fps,
        # Optional fields: a runner older than these fields still builds both
        # encoded versions, at its own default bitrates.
        "skip_high_def": skip_high_def,
        "skip_normalization": skip_normalization,
        "preset": config.MOVIE_ENCODING_PRESET,
        "vbv_bufsize_factor": config.MOVIE_VBV_BUFSIZE_FACTOR,
    }
    if bitrates is not None:
        params["highdef_bitrate"], params["lowdef_bitrate"] = bitrates
    nomad_job = config_store.get_nomad_normalize_job()
    result = remote_job.run_job(app, config, nomad_job, params)
    return result


def save_variants(
    preview_file_id,
    original_picture_path,
    with_original=True,
    remove_original=True,
):
    """
    Build the variants of a picture file and save them in the main storage.
    Record each stored variant as ok. Then remove the generated variants.
    Also remove the original, unless remove_original is False: then the
    caller owns it.
    """
    variants = thumbnail_utils.generate_preview_variants(
        original_picture_path, preview_file_id
    )
    if with_original:
        variants.append(("original", original_picture_path))
    try:
        for prefix, path in variants:
            file_store.add_picture(prefix, preview_file_id, path)
            clear_variant_from_cache(preview_file_id, prefix)
        preview_file_states_service.record_file_states(
            preview_file_id,
            {
                ("pictures", prefix): preview_file_states_service.OK
                for prefix, _ in variants
            },
        )
    finally:
        # If an upload fails, the remaining variant files must not stay.
        remove_temp_files(
            *[
                path
                for prefix, path in variants
                if remove_original or prefix != "original"
            ]
        )

    return variants


def clear_variant_from_cache(preview_file_id, prefix, extension="png"):
    """
    Remove a variant from the cache, thus the next read downloads it again
    from the object storage.
    """
    if config.FS_BACKEND != "local":
        fs.rm_file(
            fs.get_cache_file_path(config, prefix, preview_file_id, extension)
        )
    return preview_file_id


def store_preview_file_content(preview_file_id, file_path):
    """
    Save the given local file in the file storage as the content of the
    given preview file. Record it as ok and set the file size of the preview
    file.
    """
    file_store.add_file("previews", preview_file_id, file_path)
    preview_file_states_service.record_file_state(
        preview_file_id,
        "files",
        "previews",
        preview_file_states_service.OK,
    )
    file_size = fs.get_file_size(file_path)
    update_preview_file(preview_file_id, {"file_size": file_size}, silent=True)


def store_thumbnail(instance_id, picture_path, size):
    """
    Turn the given local picture into a thumbnail of the given size and save
    it in the file storage as the thumbnail of the given instance. Always
    remove the local picture.
    """
    try:
        picture_path = thumbnail_utils.turn_into_thumbnail(
            picture_path, size=size
        )
        file_store.add_picture("thumbnails", instance_id, picture_path)
    finally:
        if os.path.exists(picture_path):
            os.remove(picture_path)


def store_tile(preview_file_id, tile_path):
    """
    Save the given local tile sheet in the file storage as the tile of the
    given preview file and record it as ok.
    """
    file_store.add_picture("tiles", preview_file_id, tile_path)
    preview_file_states_service.record_file_state(
        preview_file_id,
        "pictures",
        "tiles",
        preview_file_states_service.OK,
    )


def save_preview_background_file(
    preview_background_file_id, uploaded_file, extension
):
    """
    Save the uploaded preview background file and, for an HDR file, its
    thumbnail in the file storage and clear their cached copies. Return its
    size in a dict. On a failure, remove the preview background file and
    raise WrongParameterException.
    """
    from zou.app import app as current_app

    instance_id = preview_background_file_id
    thumbnail_path = None
    try:
        tmp_folder = config.TMP_DIR
        file_name = f"{instance_id}.{extension}"
        preview_background_path = os.path.join(tmp_folder, file_name)
        uploaded_file.save(preview_background_path)
        file_size = fs.get_file_size(preview_background_path)
        file_store.add_picture(
            "preview-backgrounds", instance_id, preview_background_path
        )
        clear_variant_from_cache(instance_id, "preview-backgrounds", extension)
        if extension == "hdr":
            thumbnail_path = thumbnail_utils.turn_hdr_into_thumbnail(
                preview_background_path
            )
            file_store.add_picture("thumbnails", instance_id, thumbnail_path)
            clear_variant_from_cache(instance_id, "thumbnails")

        return {
            "preview_file_id": instance_id,
            "file_size": file_size,
        }
    except Exception:
        current_app.logger.error(
            f"Error while saving preview background file and thumbnail: {instance_id}"
        )
        deletion_service.remove_preview_background_file_by_id(
            instance_id, force=True
        )
        raise WrongParameterException(
            f"Error while saving preview background file and thumbnail: {instance_id}"
        )
    finally:
        try:
            if os.path.exists(preview_background_path):
                os.remove(preview_background_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
        except OSError:
            pass


def update_preview_file_position(preview_file_id, position):
    """
    Change the positions of the preview files of the given task and
    revision. The given position is the new position of the given preview
    file. A position out of range changes nothing. Return the preview files
    of the revision.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task_id = preview_file.task_id
    revision = preview_file.revision
    preview_files = (
        PreviewFile.query.filter_by(task_id=task_id, revision=revision)
        .order_by(PreviewFile.position, PreviewFile.created_at)
        .all()
    )
    if position > 0 and position <= len(preview_files):
        tmp_list = [p for p in preview_files if str(p.id) != preview_file_id]
        tmp_list.insert(position - 1, preview_file)
        for i, preview in enumerate(tmp_list):
            preview.update({"position": i + 1})
            files_service.clear_preview_file_cache(str(preview.id))
        # The list was read in the old order of the positions, thus it must
        # follow the move to return the revision in its new order.
        preview_files = tmp_list
    return PreviewFile.serialize_list(preview_files)


def get_preview_files_for_revision(task_id, revision):
    """
    Return all preview files for the given task and revision.
    """
    preview_files = PreviewFile.query.filter_by(
        task_id=task_id, revision=revision
    ).order_by(PreviewFile.position)
    return fields.serialize_models(preview_files)


def get_running_preview_files(cursor_preview_file_id=None, limit=None):
    """
    Return the preview files of all open productions whose status is broken,
    missing or processing. Use cursor-based pagination.
    """
    query = (
        PreviewFile.query.join(Task)
        .join(Project)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .filter(PreviewFile.status.in_(("broken", "missing", "processing")))
        .add_columns(Task.project_id, Task.task_type_id, Task.entity_id)
        .order_by(PreviewFile.created_at.desc())
    )

    if cursor_preview_file_id is not None:
        cursor_preview_file = PreviewFile.get(cursor_preview_file_id)
        if cursor_preview_file is None:
            raise WrongParameterException(
                f"No preview file found with id: {cursor_preview_file_id}"
            )
        query = query.filter(
            PreviewFile.created_at < cursor_preview_file.created_at
        )

    if limit is not None:
        query = query.limit(limit)

    entries = query.all()

    results = []
    for preview_file, project_id, task_type_id, entity_id in entries:
        result = preview_file.serialize()
        result["project_id"] = fields.serialize_value(project_id)
        result["task_type_id"] = fields.serialize_value(task_type_id)
        result["full_entity_name"], _, _ = (
            entities_service.get_full_entity_name(entity_id)
        )
        results.append(result)
    return results


def get_preview_files_for_entity(entity_id):
    """
    Return all preview files related to the given entity.
    """
    query = (
        PreviewFile.query.join(Task)
        .join(TaskType)
        .filter(Task.entity_id == entity_id)
        .order_by(
            TaskType.name, PreviewFile.revision.desc(), PreviewFile.position
        )
    )
    return [preview_file.present() for preview_file in query.all()]


def unpin_foreign_preview_files(shots):
    """
    Unset the preview file of the playlist entries that it does not belong
    to, unknown entries included: else the entry would play the preview of
    another entity. Entries are dicts that hold an entity_id (or id) and a
    preview_file_id. Other values stay as they are. Write a kept preview ID
    in lowercase, the form that the playlist reads match.
    """
    entries = [shot for shot in shots if isinstance(shot, dict)]
    preview_file_ids = {
        str(shot["preview_file_id"]).lower()
        for shot in entries
        if shot.get("preview_file_id")
        and fields.is_valid_id(shot["preview_file_id"])
    }
    entity_ids = {}
    if preview_file_ids:
        rows = (
            PreviewFile.query.join(Task, Task.id == PreviewFile.task_id)
            .filter(PreviewFile.id.in_(preview_file_ids))
            .with_entities(PreviewFile.id, Task.entity_id)
            .all()
        )
        entity_ids = {
            str(preview_file_id): str(entity_id)
            for preview_file_id, entity_id in rows
        }
    for shot in entries:
        if shot.get("preview_file_id"):
            preview_file_id = str(shot["preview_file_id"]).lower()
            entity_id = str(shot.get("entity_id") or shot.get("id")).lower()
            is_own = entity_ids.get(preview_file_id) == entity_id
            shot["preview_file_id"] = preview_file_id if is_own else None
    return shots


def get_last_preview_file_for_task(task_id):
    """
    Return the first preview file of the last revision of the given task, or
    None.
    """
    preview = (
        PreviewFile.query.filter(PreviewFile.task_id == task_id)
        .order_by(
            PreviewFile.revision.desc(),
            PreviewFile.created_at,
        )
        .first()
    )
    if preview is None:
        return None
    else:
        return preview.serialize()


def extract_frame_from_preview_file(preview_file, frame_number):
    """
    Extract one frame of a movie preview as a picture and return its path.
    Return None for an imported preview without binary. If the preview is
    not a movie or no stored version is found, raise
    PreviewFileNotFoundException.
    """
    if (preview_file.get("data") or {}).get("imported_only"):
        # Imported through sync-push: only the metadata is here. The binary
        # is in another location and comes with the file sync. Skip silently.
        return None
    project = get_project_from_preview_file(preview_file["id"])

    if preview_file["extension"] == "mp4":
        preview_file_path = locate_stored_movie(preview_file)
    else:
        raise PreviewFileNotFoundException

    fps = get_preview_file_fps(
        project, get_entity_from_preview_file(preview_file["id"])
    )
    extracted_frame_path = movie.extract_frame_from_movie(
        preview_file_path, frame_number, fps
    )

    return extracted_frame_path


def dispatch_frame_extraction(preview_file, frame_number, no_job=False):
    """
    Rebuild the variants of a movie preview from one of its frames, on the
    job queue if one is enabled. Return True if it was queued.
    """
    if config.ENABLE_JOB_QUEUE and not no_job:
        queue_store.job_queue.enqueue(
            replace_extracted_frame_for_preview_file,
            args=(preview_file, frame_number),
            job_timeout=int(config.JOB_QUEUE_TIMEOUT),
        )
        return True
    replace_extracted_frame_for_preview_file(preview_file, frame_number)
    return False


def replace_extracted_frame_for_preview_file(preview_file, frame_number):
    """
    Replace the preview thumbnail with the given frame, thus a movie can show
    the frame that the reviewer selected. If it fails, the previous thumbnail
    stays: nothing is broken, only unchanged.
    """
    from flask import has_app_context

    from zou.app import app

    def run():
        try:
            extracted_frame_path = extract_frame_from_preview_file(
                preview_file, frame_number
            )
            if extracted_frame_path is None:
                return
            extracted_frame_path = thumbnail_utils.turn_into_thumbnail(
                extracted_frame_path
            )
            save_variants(preview_file["id"], extracted_frame_path)
        except Exception:
            app.logger.error(
                f"Could not extract frame {frame_number} of preview file "
                f"{preview_file['id']}",
                exc_info=True,
            )

    if has_app_context():
        run()
    else:
        with app.app_context():
            run()


def extract_tile_from_preview_file(preview_file):
    """
    Build the tile sheet of a movie preview and return its path. The tile
    sheet is the strip of thumbnails that the player scrubs on. Return None
    for an imported preview without binary.
    """
    if (preview_file.get("data") or {}).get("imported_only"):
        # Imported through sync-push: metadata only. Skip silently.
        return None
    if preview_file["extension"] == "mp4":
        # A tile is 100 pixels high: the low def movie is enough.
        preview_file_path = locate_stored_movie(preview_file, lowdef=True)
        extracted_tile_path = movie.generate_tile(preview_file_path)
        return extracted_tile_path
    else:
        raise WrongParameterException("Preview file is not a movie")


def retrieve_stored_movie(preview_file):
    """
    Return the local path of the smallest stored version of a movie, low def
    first, or None if no version could be fetched. A tile is 100 pixels
    high: the high def movie only makes the decode longer.
    """
    recorded_prefixes = files_service.get_preview_file_data(preview_file).get(
        files_service.MOVIE_PREFIXES_KEY
    )
    for prefix in files_service.get_movie_prefixes(
        recorded_prefixes or [], True
    ):
        movie_path = retrieve_preview_file(
            config, file_store, prefix, preview_file
        )
        if movie_path is not None:
            return movie_path
    return None


def get_stored_movie_prefixes(preview_file, lowdef=False):
    """
    Return the storage prefixes to try for the movie of the given preview
    file dict, best first. The normalization settings decide which versions
    exist (SKIP_NORMALIZATION_HIGHDEF keeps lowdef only,
    SKIP_NORMALIZATION_FULL with PREVIEW_SAVE_SOURCE_FILE keeps the source
    only). Thus no reader can assume the "previews" prefix.
    """
    data = preview_file.get("data") or {}
    recorded = data.get(files_service.MOVIE_PREFIXES_KEY) or []
    return files_service.get_movie_prefixes(recorded, lowdef)


def locate_stored_movie(preview_file, lowdef=False):
    """
    Return the local path of a stored version of the movie of the given
    preview file dict. Fetch it from the store if necessary. If the store
    holds none of the versions, raise PreviewFileNotFoundException. Only an
    absence that the store confirmed moves on to the next version. A
    temporary failure is raised as is: else a caller that records the size
    of the movie would store the size of the low def version.
    """
    preview_file_id = str(preview_file["id"])
    for prefix in get_stored_movie_prefixes(preview_file, lowdef):
        try:
            return fs.get_file_path_and_file(
                config,
                file_store.get_local_movie_path,
                file_store.open_movie,
                prefix,
                preview_file_id,
                "mp4",
            )
        except fs.ConfirmedFileNotFound:
            continue
    raise PreviewFileNotFoundException(
        f"No stored movie for preview file {preview_file_id}."
    )


def retrieve_preview_file(config, file_store, prefix, preview_file):
    """
    Fetch a preview binary from the store to a local path, for all storage
    backends.
    """
    try:
        preview_file_path = fs.get_file_path_and_file(
            config,
            (
                file_store.get_local_movie_path
                if preview_file.extension == "mp4"
                else file_store.get_local_picture_path
            ),
            (
                file_store.open_movie
                if preview_file.extension == "mp4"
                else file_store.open_picture
            ),
            prefix,
            str(preview_file.id),
            preview_file.extension,
        )
    except Exception as e:
        logger.warning(f"Failed to get preview file {preview_file.id}: {e}.")
        return None
    return preview_file_path


def generate_thumbnails(preview_file, preview_file_path, total, index):
    """
    Generate the thumbnail variants of one preview again and store them. If
    it fails, log the failure and do not raise it.
    """
    try:
        original_picture_path = preview_file_path
        if preview_file.extension == "mp4":
            original_picture_path = movie.generate_thumbnail(preview_file_path)
        save_variants(
            preview_file.id, original_picture_path, with_original=False
        )
        logger.info(
            f"{index:0{len(str(total))}}/{total} Thumbnails generated for {preview_file.id}.",
        )
    except Exception as e:
        logger.warning(
            f"Failed to generate thumbnails for {preview_file.id}: {e}."
        )


def generate_tiles(
    file_store, preview_file, preview_file_path, total, index, force=False
):
    """
    Generate the tile sheet of one movie preview again and store it, unless
    a tile is already stored and force is False. If it fails, record and log
    the failure, and do not raise it.
    """
    try:
        if preview_file.extension == "mp4" and (
            force
            or not file_store.exists_picture("tiles", str(preview_file.id))
        ):
            tile_path = movie.generate_tile(preview_file_path)
            store_tile(preview_file.id, tile_path)
            # The tile is stored. A failure to remove the local temporary
            # copy is not a generation failure and must not undo the
            # "ok" that was recorded above.
            try:
                os.remove(tile_path)
            except OSError:
                pass
            logger.info(
                f"{index:0{len(str(total))}}/{total} Tile "
                + f"generated for {preview_file.id}.",
            )
    except Exception as e:
        if preview_file.extension == "mp4":
            preview_file_states_service.record_file_state(
                preview_file.id,
                "pictures",
                "tiles",
                preview_file_states_service.FAILED,
            )
        logger.warning(
            f"Failed to generate tile for preview file {preview_file.id}: {e}."
        )


def copy_preview_file_on_storage(
    bucket_name,
    get_path_func,
    exists_func,
    copy_func,
    prefix,
    original_preview_file_id,
    preview_file_to_update_id,
):
    """
    Copy one stored preview to another prefix. If the target already holds
    it, skip the copy. Return True if a file was copied.
    """
    if config.FS_BACKEND == "local":
        file_path = get_path_func(prefix, original_preview_file_id)
        other_file_path = get_path_func(prefix, preview_file_to_update_id)
        if os.path.exists(file_path):
            # Recorded before the copy, as file_store._copy does: a target
            # key marked as deleted must be revived before the write.
            stored_files_service.record_write(
                bucket_name, prefix, preview_file_to_update_id
            )
            os.makedirs(os.path.dirname(other_file_path), exist_ok=True)
            shutil.copyfile(file_path, other_file_path)
            return True
    elif exists_func(prefix, original_preview_file_id):
        copy_func(
            prefix, original_preview_file_id, prefix, preview_file_to_update_id
        )
        return True
    return False


def get_preview_file_name(preview_file_id):
    """
    Build a unique and human readable file name for preview downloads. The
    name follows this convention:
    [project_name]_[entity_name]_[task_type_name]_v[revision].[extension].
    If the organisation uses original file names, use the original name. If
    the position is above 1, add a -[position] suffix.
    """
    organisation = organisation_service.get_organisation()
    preview_file = files_service.get_preview_file(preview_file_id)
    task = tasks_service.get_task(preview_file["task_id"])
    task_type = task_types_service.get_task_type(task["task_type_id"])
    project = projects_service.get_project(task["project_id"])
    entity_name, _, _ = entities_service.get_full_entity_name(
        task["entity_id"]
    )

    if (
        organisation["use_original_file_name"]
        and preview_file.get("original_name", None) is not None
    ):
        name = preview_file["original_name"]
    else:
        name = (
            f"{project['name']}_{entity_name}_{task_type['name']}_v"
            f"{preview_file['revision']}"
        )
        name = slugify.slugify(name, separator="_")
    if (preview_file.get("position", 0) or 0) > 1:
        name = f"{name}-{preview_file['position']}"
    return f"{name}.{preview_file['extension']}"
