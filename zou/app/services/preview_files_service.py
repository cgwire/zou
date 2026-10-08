import logging
import os
import shutil
import time


import ffmpeg
import redis
from rq import Queue, Retry, get_current_job
from rq.timeouts import BaseTimeoutException

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from zou.app import config
from zou.app.stores import (
    config_store,
    file_store,
    queue_store,
)

from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project, ProjectTaskTypeLink
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    files_service,
    preview_file_states_service,
    projects_service,
    stored_files_service,
    tasks_service,
    entities_service,
    organisation_service,
    task_types_service,
)
from zou.utils import movie
from zou.app.utils import (
    events,
    fields,
    remote_job,
    thumbnail as thumbnail_utils,
)
from zou.app.exceptions import (
    WrongParameterException,
    PreviewFileNotFoundException,
    PreviewProcessingFailedException,
)
from zou.app.utils import fs
import slugify

logger = logging.getLogger(__name__)


REMOTE_NORMALIZE_VERSION = 2
# Seconds before each new attempt of a preview processing job whose
# upload to the object storage failed on authentication (Keystone down).
# Meanwhile the uploaded file waits in PENDING_UPLOADS_FOLDER, which the
# TMP_DIR cleaning skips, and the preview file stays "processing".
STORAGE_RETRY_INTERVALS = (60, 300, 900, 3600)
STORAGE_RETRIES_META_KEY = "storage_retries"
PENDING_UPLOADS_FOLDER = "pending-uploads"


def get_preview_file_dimensions(project, entity=None):
    """
    Return dimensions set at entity level or project level or default
    dimensions if the dimensions are not set.
    Entity resolution has priority over project resolution.
    The default size is based on 1080 height
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
        # Defensive fallback: a malformed resolution string should not
        # crash the normalization worker, just use the default 1080.
        from zou.app import app as current_app

        current_app.logger.warning(
            "Invalid resolution %r, falling back to default", resolution
        )
        width = None
        height = 1080

    return (width, height)


def get_preview_file_fps(project, entity=None):
    """
    Return fps set at project level or default fps if the dimensions are not
    set.
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
    Get project dict of related preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)

    task = Task.get(preview_file.task_id)
    project = Project.get(task.project_id)
    return project.serialize()


def get_task_type_link_from_preview_file(preview_file_id):
    """
    Get the project task type link dict of related preview file, or None
    when the task type is not linked to the project.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task = Task.get(preview_file.task_id)
    link = ProjectTaskTypeLink.get_by(
        project_id=task.project_id, task_type_id=task.task_type_id
    )
    return link.serialize() if link is not None else None


def get_entity_from_preview_file(preview_file_id):
    """
    Get entity dict of related preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task = Task.get(preview_file.task_id)
    entity = Entity.get(task.entity_id)
    return entity.serialize()


def update_preview_file(preview_file_id, data, silent=False):
    """
    Update given preview file and notify the clients, unless silent.
    """
    # Job workers may hit a transient database error right after the
    # request that created the row committed; that is what the retries
    # are for. A row that is not there will not appear in six seconds.
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


def update_preview_file_raw(preview_file, data, silent=False):
    """
    Same as update_preview_file, on an active record already loaded.
    """
    # Read the id while the instance is still live: on StaleDataError,
    # base.update() rolls the session back, which expires every attribute.
    # Reading preview_file.id afterwards reloads the (now deleted) row and
    # raises ObjectDeletedError, masking the real error.
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
    if not silent:
        task = Task.get(preview_file.task_id)
        event_data = {"preview_file_id": preview_file_id}
        # The clients wait for the status to ask again for the pictures a
        # job builds in the background. A metadata refresh of a ready
        # preview leaves it out: the maintenance commands refresh them all,
        # and every client would fetch every picture again.
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
    Mark given preview file as broken.
    """
    return update_preview_file(preview_file_id, {"status": "broken"})


def set_preview_file_as_missing(preview_file_id):
    """
    Mark a preview file as missing: its source binary is gone from
    storage and renormalization is no longer possible.
    """
    return update_preview_file(preview_file_id, {"status": "missing"})


def remove_temp_files(*paths):
    """
    Remove movie processing temp files, ignoring the ones already gone.
    """
    for path in paths:
        if path is not None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


def get_pending_upload_path(upload_path):
    """
    Where an upload waits for the object storage to come back, under
    TMP_DIR so that moving it there is a rename.
    """
    return os.path.join(
        config.TMP_DIR, PENDING_UPLOADS_FOLDER, os.path.basename(upload_path)
    )


def _resolve_upload_path(upload_path):
    """
    A job queued again after a storage failure keeps its arguments: find
    the upload in the pending folder when it was moved there.
    """
    if upload_path is None or os.path.exists(upload_path):
        return upload_path
    pending_path = get_pending_upload_path(upload_path)
    if os.path.exists(pending_path):
        return pending_path
    return upload_path


def is_scheduler_running(job):
    """
    Tell whether a worker started with --with-scheduler serves the queue
    of the job: a job queued again with a delay lands in the scheduled
    registry, which only the scheduler moves back to the queue. It holds
    a lock in Redis while running, which expires shortly after it stops.
    """
    try:
        queue = Queue(job.origin, connection=job.connection)
        return queue.scheduler_pid is not None
    except redis.RedisError:
        return False


def _requeue_on_storage_failure(exc, upload_path):
    """
    Keep the upload aside and return the Retry that queues the running
    job again, when it failed on the object storage authentication and
    attempts remain. Return None otherwise: no job (inline processing),
    another error, attempts exhausted or no scheduler to queue the job
    again after the delay, the caller fails as usual.
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
    # The next attempt starts over: a Nomad job dispatched by this one
    # must not be resumed as if the source were stored.
    job.meta.pop(remote_job.NOMAD_JOB_ID_META_KEY, None)
    job.save_meta()
    # Retry.max counts every retry of the job, handovers included.
    return Retry(
        max=(job.number_of_retries or 0) + 1,
        interval=STORAGE_RETRY_INTERVALS[attempt],
    )


def mark_broken_on_job_failure(
    job, connection, exc_type, exc_value, traceback
):
    """
    RQ failure callback for the movie normalization and picture variant
    jobs: mark the preview file as broken and drop its temporary file.
    Without it, a job killed by timeout or a dead worker leaves the
    preview file stuck on "processing" forever.
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
    Run prepare_and_store_movie on the job queue when one is enabled, in
    the calling thread otherwise. A raw store is cheap enough to stay
    synchronous, but the remote worker blocks until Nomad is done and is
    what builds the thumbnails even without normalization: it never runs
    in a request thread.
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
    Turn an uploaded movie into a ready preview file: keep the source when
    asked, encode the preview versions (here or on the remote worker),
    build the thumbnails and the tile, then record the metadata and which
    versions are stored. Any failure marks the preview file as broken
    (the job timeout goes through, so that rq records the failure), and
    the temporary files are removed whatever happens.
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
            # The worker stops: the next one resumes the job and reads the
            # upload again.
            temp_files.remove(uploaded_movie_path)
            raise
        except BaseTimeoutException:
            # rq raises its timeout inside the job: swallowed, the job
            # would count as successful and mark_broken_on_job_failure
            # would never run.
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
    Build the picture variants on the job queue when one is enabled, in
    the calling thread otherwise. Return whether the work was queued, so
    the caller knows whether the preview file is still processing.

    Like the movie pipeline, the job receives a local path: the workers
    run on the API host, or share TMP_DIR with it.
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
    preview file ready. Runs from a job as well as from a request: it
    brings its own app context when there is none.
    """
    from flask import has_app_context
    from zou.app import app

    original_picture_path = _resolve_upload_path(original_picture_path)

    def run():
        keep_original = False
        try:
            # Kept on failure: a job queued again uploads it once more.
            save_variants(
                preview_file_id, original_picture_path, remove_original=False
            )
            preview_file = update_preview_file(
                preview_file_id, {"status": "ready"}
            )
            tasks_service.update_preview_file_info(preview_file)
        except PreviewFileNotFoundException:
            # Deleted while the job waited in the queue: nothing to build.
            app.logger.warning(
                f"Preview file {preview_file_id} was deleted before its "
                f"variants could be built"
            )
        except BaseTimeoutException:
            # rq raises its timeout inside the job: swallowed, the job
            # would count as successful and mark_broken_on_job_failure
            # would never run.
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
            # Covers the inline path (no job queue, or ?no_job=true): the
            # queued path relies on on_failure=mark_broken_on_job_failure,
            # but that callback never runs for a call made directly from
            # the request thread. Marking broken here first, then
            # re-raising, keeps both paths consistent and leaves rq's
            # failure handling (which is idempotent) intact.
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
    The movie pipeline itself, one step after the other. Every temporary
    file it produces goes into temp_files, removed by the caller.
    """
    # A job resumed after a handover stored the source already.
    if add_source_to_file_store and not remote_job.is_resumed():
        file_store.add_movie("source", preview_file_id, uploaded_movie_path)
    _record_original_metadata(preview_file_id, uploaded_movie_path)
    fps, width, height, bitrates = _get_encoding_parameters(preview_file_id)

    # SKIP_NORMALIZATION_FULL turns every upload into a raw store, as if
    # the client had asked for normalize=false. SKIP_NORMALIZATION_HIGHDEF
    # only drops the 28M encoding: the low def version is still built and
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
        # The upload is the preview. It only goes under `previews` when it
        # was not already stored as the source: the movie routes fall back
        # from one to the other, so a second copy buys nothing.
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
    Keep the size and duration of the upload before it is encoded. A
    nice-to-have: a failure here must not block the pipeline, and the
    update is silent so the clients only hear about the final "ready" one.
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
    The fps, the resolution and the (highdef, lowdef) bitrates the previews
    are encoded at, from the project, the entity or the task type link
    overriding them. The job can start before the upload's transaction is
    visible to it: one retry covers that. Still missing after it, the preview
    file was deleted while the job waited.
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
    Encode the preview versions with ffmpeg and store them. Return the
    movie the metadata and the thumbnails are read from: the high def
    one, or the low def one when the high def is skipped.
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
    Hand the movie over to the remote worker, which reads the source from
    the storage, encodes it and builds the thumbnails and the tile. It
    runs even when nothing has to be encoded. Return the movie the
    metadata is read from: the encoded version fetched back from the
    storage, or the upload itself when nothing was encoded.
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
    # The fetch lands on the movie routes' cache path. A copy of a
    # previous encoding may already sit there (the movie was played on
    # this host, then renormalized) and would be read instead of the
    # fresh one: evict it first. The copy does not stay either: the
    # worker may not be a web host, and nothing evicts that cache.
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
    Register the files the remote worker may store, before it runs: the
    objects a failed job leaves behind are known too. The tile is in:
    its build may fail without failing the job, a row without its object
    is harmless.
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
    The fields recorded on the preview file once it is ready.
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
    Build the picture variants and the tile mosaic from the movie and
    store them. A missing tile is logged, not fatal.
    """
    from zou.app import app as current_app

    original_picture_path = movie.generate_thumbnail(movie_path)
    temp_files.append(original_picture_path)
    thumbnail_utils.turn_into_thumbnail(original_picture_path, size)
    save_variants(preview_file_id, original_picture_path)
    current_app.logger.info(f"thumbnail created {original_picture_path}")

    try:
        tile_path = movie.generate_tile(movie_path)
        file_store.add_picture("tiles", preview_file_id, tile_path)
        preview_file_states_service.record_file_state(
            preview_file_id,
            "pictures",
            "tiles",
            preview_file_states_service.OK,
        )
        # The tile is stored: a failure removing the local temp copy is
        # not a generation failure and must not undo the "ok" just
        # recorded above.
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
    Which storage prefixes hold the movie, recorded on the preview file so
    that the movie routes do not have to rediscover it by probing the
    storage. Locally it follows from the flags: the encoded versions, or
    the upload itself under `previews` when it was stored raw and not
    already kept as the source. A remote job is asked nothing: a runner
    that predates skip_high_def still uploads both encoded versions, so
    the storage is probed once instead.
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
    Record the movie versions stored and, when a remote job built them,
    which pictures it actually wrote: a picture it should have written
    and did not is failed. A local build records its pictures as it
    stores them. A version not produced is not recorded missing: another
    writer may still bring it, only a read confirms an absence.
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
    Movie processing runs on a remote worker when the job queue is set to
    remote and a Nomad job name is configured.
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
    Hand the movie processing over to a remote worker and wait for it. The
    worker also builds the thumbnails and the tile, so it is dispatched even
    when no encoding is wanted.
    """
    params = {
        "version": str(REMOTE_NORMALIZE_VERSION),
        "preview_file_id": preview_file_id,
        "width": width,
        "height": height,
        "fps": fps,
        # Optional fields: a runner that predates them keeps building both
        # encoded versions as before, at its own default bitrates.
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
    Build variants of a picture file and save them in the main storage.
    The generated variants are removed afterwards, the original too
    unless remove_original is False: the caller then owns it.
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
        # A failed upload must not leak the remaining variant files.
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
    Clear a variant from the cache to force to redownload from object storage.
    """
    if config.FS_BACKEND != "local":
        fs.rm_file(
            fs.get_cache_file_path(config, prefix, preview_file_id, extension)
        )
    return preview_file_id


def update_preview_file_position(preview_file_id, position):
    """
    Change positions for preview files of given task and revision.
    Given position is the new position for given preview file.
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
        # The list was read in the order the positions used to be in, so it
        # has to follow the move to answer the revision in its new order.
        preview_files = tmp_list
    return PreviewFile.serialize_list(preview_files)


def get_preview_files_for_revision(task_id, revision):
    """
    Get all preview files for given task and revision.
    """
    preview_files = PreviewFile.query.filter_by(
        task_id=task_id, revision=revision
    ).order_by(PreviewFile.position)
    return fields.serialize_models(preview_files)


def get_running_preview_files(cursor_preview_file_id=None, limit=None):
    """
    Return preview files for all productions with status equals to broken,
    missing or processing using cursor-based pagination.
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
    Return all preview files related to given entity.
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
    Unset the preview file of the playlist entries it does not belong to,
    unknown ones included: the entry would play another entity's preview.
    Entries are dicts holding an entity_id (or id) and a preview_file_id,
    other values are left as they are. A kept preview id is written in
    lowercase, the form the playlist reads match.
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
    Get last preview published for given task.
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
    Extract one frame of a movie preview as a picture.
    """
    if (preview_file.get("data") or {}).get("imported_only"):
        # Imported via sync-push: only metadata is here, the binary lives
        # elsewhere and will arrive via the file sync. Skip silently.
        return None
    try:
        project = get_project_from_preview_file(preview_file["id"])
    except PreviewFileNotFoundException:
        raise PreviewFileNotFoundException

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
    Rebuild the variants of a movie preview from one of its frames, on
    the job queue when one is enabled. Return whether it was queued.
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
    Replace the preview thumbnail with given frame, so a movie can show
    the frame the reviewer picked. A failure leaves the previous
    thumbnail in place: nothing is broken, only unchanged.
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
    Build the tile sheet of a movie preview, the strip of thumbnails the
    player scrubs on.
    """
    if (preview_file.get("data") or {}).get("imported_only"):
        # Imported via sync-push: metadata only. Skip silently.
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
    Local path of the smallest stored version of a movie, low def first,
    or None when the storage holds none of them. A tile is 100 pixels
    high: the high def movie only costs a longer decode.
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
    Storage prefixes to try for the movie of given preview file dict, best
    first. The normalization settings decide which versions exist
    (SKIP_NORMALIZATION_HIGHDEF keeps lowdef only, SKIP_NORMALIZATION_FULL
    with PREVIEW_SAVE_SOURCE_FILE keeps the source only), so no reader may
    assume the "previews" one.
    """
    data = preview_file.get("data") or {}
    recorded = data.get(files_service.MOVIE_PREFIXES_KEY) or []
    return files_service.get_movie_prefixes(recorded, lowdef)


def locate_stored_movie(preview_file, lowdef=False):
    """
    Local path of a stored version of the movie of given preview file dict,
    fetched from the store when needed. Raises PreviewFileNotFoundException
    when the store holds none of the versions. Only an absence the store
    confirmed moves on to the next version: a transient failure is raised
    as is, a caller recording the size of the movie would otherwise store
    the one of the low def version.
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
    Fetch a preview binary from the store to a local path, whichever
    backend holds it.
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
    Regenerate the thumbnail variants of one preview and store them.
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
    Regenerate the tile sheet of one movie preview and store it.
    """
    try:
        if preview_file.extension == "mp4" and (
            force
            or not file_store.exists_picture("tiles", str(preview_file.id))
        ):
            tile_path = movie.generate_tile(preview_file_path)
            file_store.add_picture("tiles", preview_file.id, tile_path)
            preview_file_states_service.record_file_state(
                preview_file.id,
                "pictures",
                "tiles",
                preview_file_states_service.OK,
            )
            # The tile is stored: a failure removing the local temp copy
            # is not a generation failure and must not undo the "ok"
            # just recorded above.
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
    Copy one stored preview to another prefix, skipping the copy when the
    target already holds it. Return True when a file was actually copied.
    """
    if config.FS_BACKEND == "local":
        file_path = get_path_func(prefix, original_preview_file_id)
        other_file_path = get_path_func(prefix, preview_file_to_update_id)
        if os.path.exists(file_path):
            # Recorded before the copy, as file_store._copy does: a target
            # key marked deleted must be revived before it is written.
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
    Build unique and human readable file name for preview downloads. The
    convention followed is:
    [project_name]_[entity_name]_[task_type_name]_v[revivision].[extension].
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
