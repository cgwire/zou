import logging
import os
import redis
from collections import Counter
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import ObjectDeletedError

from zou.app import config
from zou.app.stores import config_store, file_store, queue_store, redis_client
from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.preview_file_storage_state import PreviewFileStorageState
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.services import (
    files_service,
    preview_file_states_service,
    shots_service,
    projects_service,
    stored_files_service,
    entity_types_service,
    preview_files_service,
)
from zou.utils import movie
from zou.app.utils import fields, remote_job, thumbnail as thumbnail_utils, fs
from zou.app.exceptions import (
    JobQueueDisabledException,
    ProjectNotFoundException,
    EpisodeNotFoundException,
)
from zou.app.utils.progress import NullProgress

logger = logging.getLogger(__name__)

REMOTE_TILE_VERSION = 1
# Seconds before a missing tile sheet is built again for the same movie.
TILE_RETRY_DELAY = 3600
# Held by the local tile build in progress: one ffmpeg decode at a time
# next to the API.
LOCAL_TILE_BUILD_LOCK_KEY = "tile-build:local"


def _get_preview_files_to_reset(extension):
    """
    Return the usable preview files of open projects with given extension:
    the ones whose metadata can be read back from storage.
    """
    return (
        PreviewFile.query.join(Task)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .filter(PreviewFile.status.not_in(("broken", "missing", "processing")))
        .filter(PreviewFile.extension == extension)
    )


def reset_movie_files_metadata():
    """
    Reset preview files size informations of open projects.
    """
    for preview_file in _get_preview_files_to_reset("mp4"):
        try:
            preview_file_path = preview_files_service.locate_stored_movie(
                {
                    "id": str(preview_file.id),
                    "extension": "mp4",
                    "data": files_service.get_preview_file_data(preview_file),
                }
            )
            file_size = os.path.getsize(preview_file_path)
            width, height = movie.get_movie_size(preview_file_path)
            duration = float(movie.get_movie_duration(preview_file_path))
            preview_files_service.update_preview_file_raw(
                preview_file,
                {
                    "width": width,
                    "height": height,
                    "file_size": file_size,
                    "duration": duration,
                },
            )
            logger.info(
                f"Size information stored for preview file {preview_file.id}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to store information for preview file {preview_file.id}: {e}"
            )


def reset_picture_files_metadata():
    """
    Reset preview files size informations of open projects.
    """
    for preview_file in _get_preview_files_to_reset("png"):
        try:
            preview_file_path = fs.get_file_path_and_file(
                config,
                file_store.get_local_picture_path,
                file_store.open_picture,
                "original",
                str(preview_file.id),
                "png",
            )
            width, height = thumbnail_utils.get_dimensions(preview_file_path)
            file_size = os.path.getsize(preview_file_path)
            preview_files_service.update_preview_file_raw(
                preview_file,
                {
                    "width": width,
                    "height": height,
                    "file_size": file_size,
                },
            )
            logger.info(
                f"Size information stored for preview file {preview_file.id}",
            )
        except Exception as e:
            logger.warning(
                f"Failed to store information for preview file {preview_file.id}: {e}"
            )


def _build_preview_extra_query(
    project=None,
    entity_id=None,
    episodes=None,
    only_shots=False,
    only_assets=False,
    extensions=("mp4", "png"),
):
    """
    The ready previews of the open projects the preview extra commands
    work on, narrowed by project, entity, episodes and entity kind.
    """
    if episodes is None:
        episodes = []
    query = (
        PreviewFile.query.join(Task)
        .join(Entity)
        .join(Project)
        .join(ProjectStatus, Project.project_status_id == ProjectStatus.id)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .filter(PreviewFile.status.not_in(("broken", "missing", "processing")))
        .filter(PreviewFile.extension.in_(extensions))
    )
    project_id = None
    if project is not None:
        try:
            project_id = projects_service.get_project_by_name(project)["id"]
        except ProjectNotFoundException:
            project_id = projects_service.get_project(project)["id"]
        query = query.filter(Project.id == project_id)

    if entity_id is not None:
        query = query.filter(Task.entity_id == entity_id)

    if episodes:
        get_episode_by_name = project is not None
        episode_ids = []
        for episode in episodes:
            try:
                episode_id = shots_service.get_episode(episode)["id"]
            except EpisodeNotFoundException as e:
                if get_episode_by_name:
                    episode_id = shots_service.get_episode_by_name(
                        project_id, episode
                    )["id"]
                else:
                    raise e
            episode_ids.append(episode_id)
        Sequence = aliased(Entity)
        query = query.join(Sequence, Sequence.id == Entity.parent_id).filter(
            Sequence.parent_id.in_(episode_ids)
        )
    if only_shots:
        query = query.filter(
            Entity.entity_type_id == entity_types_service.get_shot_type()["id"]
        )
    elif only_assets:
        query = query.filter(
            Entity.entity_type_id.not_in(
                entity_types_service.get_temporal_type_ids()
            )
        )
    return query


def queue_missing_tiles(
    project=None,
    entity_id=None,
    episodes=None,
    only_shots=False,
    only_assets=False,
    limit=None,
    force=False,
    progress=None,
):
    """
    Queue the tile build of the movies that have none, one job per movie:
    on Nomad when a tile job is configured, on this host otherwise. The
    command itself decodes nothing and does not wait for the builds.

    The movies whose tile is recorded as stored are left out of the
    query. The recorded state answers for the other movies it knows; the
    rest cost one storage round trip, whose answer is recorded on the
    way. A movie attempted within the hour is skipped unless force is
    set. The limit caps the jobs queued, newest movies first. Return the
    counts per outcome.
    """
    if not config.ENABLE_JOB_QUEUE:
        raise JobQueueDisabledException(
            "No job queue: tiles cannot be built in the background. "
            "Use --with-tiles to build them in this command instead."
        )
    query = _build_preview_extra_query(
        project=project,
        entity_id=entity_id,
        episodes=episodes,
        only_shots=only_shots,
        only_assets=only_assets,
        extensions=("mp4",),
    )
    bucket, prefix = preview_file_states_service.TILE
    stored_tile = PreviewFileStorageState.query.filter(
        PreviewFileStorageState.preview_file_id == PreviewFile.id,
        PreviewFileStorageState.bucket == bucket,
        PreviewFileStorageState.prefix == prefix,
        PreviewFileStorageState.state == preview_file_states_service.OK,
    ).exists()
    query = query.filter(~stored_tile).order_by(
        PreviewFile.created_at.desc(), PreviewFile.id
    )

    progress = progress or NullProgress()
    summary = Counter()
    preview_files = query.all()
    progress.start(len(preview_files))
    try:
        for preview_file in preview_files:
            if limit is not None and summary["queued"] >= limit:
                break
            _queue_missing_tile(preview_file, summary, force)
            progress.advance()
    finally:
        progress.stop()
    return summary


def _queue_missing_tile(preview_file, summary, force):
    """
    Queue the tile build of one movie, counting the outcome.
    """
    try:
        preview_file_id = str(preview_file.id)
    except ObjectDeletedError:
        return
    summary["checked"] += 1
    stored = _has_stored_tile(preview_file_id)
    if stored is None:
        summary["storage_errors"] += 1
        return
    if stored:
        summary["stored"] += 1
        return
    if force:
        _tile_store().delete(_tile_attempt_key(preview_file_id))
    if generate_tile_later(preview_file_id):
        summary["queued"] += 1
    else:
        summary["recently_attempted"] += 1


def _has_stored_tile(preview_file_id):
    """
    Whether the tile of a movie is stored, from the recorded state when
    there is one, from the storage otherwise. None when the storage
    could not answer: a transient failure records nothing and queues
    nothing.
    """
    states = preview_file_states_service.get_file_states(preview_file_id)
    state = preview_file_states_service.get_state(states, "pictures", "tiles")
    if state is not None:
        return state == preview_file_states_service.OK
    probed = preview_file_states_service.probe_file_states(
        preview_file_id, "mp4", files=[preview_file_states_service.TILE]
    )
    if not probed:
        return None
    preview_file_states_service.record_file_states(preview_file_id, probed)
    return (
        probed[preview_file_states_service.TILE]
        == preview_file_states_service.OK
    )


def generate_preview_extra(
    project=None,
    entity_id=None,
    episodes=None,
    only_shots=False,
    only_assets=False,
    force_regenerate_tiles=False,
    with_tiles=False,
    with_metadata=False,
    with_thumbnails=False,
    progress=None,
):
    """
    Generate tiles for all movie previews and reset previews file size
    informations of open projects.
    """
    progress = progress or NullProgress()
    logger.info("Generating preview extras...")
    query = _build_preview_extra_query(
        project=project,
        entity_id=entity_id,
        episodes=episodes,
        only_shots=only_shots,
        only_assets=only_assets,
    )

    total = query.count()
    logger.info(f"{total} previews found.")
    progress.start(total)
    for index, preview_file in enumerate(query.all()):
        try:
            preview_file_id = str(preview_file.id)
        except ObjectDeletedError:
            progress.advance()
            continue
        if preview_file.extension == "mp4":
            prefixes = preview_files_service.get_stored_movie_prefixes(
                {"data": files_service.get_preview_file_data(preview_file)}
            )
        else:
            prefixes = ["original"]
        if config.FS_BACKEND != "local":
            preview_file_already_in_cache = any(
                os.path.isfile(
                    os.path.join(
                        config.TMP_DIR,
                        f"cache-{prefix}-{preview_file_id}"
                        f".{preview_file.extension}",
                    )
                )
                for prefix in prefixes
            )
        try:
            preview_file_path = None
            if preview_file.extension == "mp4":
                try:
                    preview_file_path = (
                        preview_files_service.locate_stored_movie(
                            {
                                "id": preview_file_id,
                                "data": files_service.get_preview_file_data(
                                    preview_file
                                ),
                            }
                        )
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to get preview file {preview_file_id}: {e}."
                    )
            else:
                preview_file_path = (
                    preview_files_service.retrieve_preview_file(
                        config, file_store, "original", preview_file
                    )
                )
            if with_tiles:
                preview_files_service.generate_tiles(
                    file_store,
                    preview_file,
                    preview_file_path,
                    total,
                    index + 1,
                    force=force_regenerate_tiles,
                )
            if with_metadata:
                _reset_preview_file_metadata(
                    preview_file, preview_file_path, total, index + 1
                )
            if with_thumbnails:
                preview_files_service.generate_thumbnails(
                    preview_file, preview_file_path, total, index + 1
                )
        finally:
            if (
                config.FS_BACKEND != "local"
                and not preview_file_already_in_cache
            ):
                try:
                    if preview_file_path is not None:
                        os.remove(preview_file_path)
                except OSError:
                    pass
        progress.advance()

    progress.stop()
    logger.info("Extra information generated.")
    return total


def generate_tile_later(preview_file_id):
    """
    Build the missing tile sheet of a movie on the job queue. Without a
    queue nothing happens: the web process runs no ffmpeg of its own. An
    attempt younger than an hour, running or failed, is not repeated: a
    Redis key remembers it, shared by every process and kept across a
    reboot, so a movie ffmpeg cannot tile does not cost a job per hover on
    the progress bar.
    """
    if not config.ENABLE_JOB_QUEUE:
        return False
    try:
        is_first_attempt = _tile_store().set(
            _tile_attempt_key(preview_file_id),
            1,
            nx=True,
            ex=TILE_RETRY_DELAY,
        )
    except redis.RedisError:
        return False
    if not is_first_attempt:
        return False
    queue_store.job_queue.enqueue(
        generate_missing_tile,
        args=(preview_file_id,),
        job_timeout=int(config.JOB_QUEUE_TIMEOUT),
    )
    return True


def is_remote_tile_enabled():
    """
    Tile sheets are built on a remote worker when the job queue is set to
    remote and a Nomad tile job is configured.
    """
    return (
        config.ENABLE_JOB_QUEUE_REMOTE
        and len(config_store.get_nomad_tile_job()) > 0
    )


def generate_missing_tile(preview_file_id):
    """
    Build and store the tile sheet of a ready movie that has none: on
    Nomad when a tile job is configured, locally otherwise. Runs under its
    own app context: it is a job.
    """
    from zou.app import app

    with app.app_context():
        preview_file = files_service.get_preview_file(preview_file_id)
        if (
            preview_file["extension"] != "mp4"
            or preview_file["status"] != "ready"
        ):
            return False
        preview_file_raw = files_service.get_preview_file_raw(preview_file_id)
        if is_remote_tile_enabled():
            return _run_remote_tile_job(app, preview_file_raw)
        return _generate_missing_tile_locally(preview_file_raw)


def _run_remote_tile_job(app, preview_file):
    """
    Hand the tile build over to the Nomad runner and wait for it. The
    runner tries the recorded prefixes first, then the others.
    """
    recorded_prefixes = files_service.get_preview_file_data(preview_file).get(
        files_service.MOVIE_PREFIXES_KEY
    )
    params = {
        "version": str(REMOTE_TILE_VERSION),
        "preview_file_id": str(preview_file.id),
        "movie_prefixes": recorded_prefixes or [],
    }
    # A Nomad dispatch error or a timeout is transient: the tile state
    # must stay as it was, not be recorded failed. Only a job that
    # actually completed without producing the tile counts as failed,
    # below.
    stored_files_service.record_remote_writes(
        [(*preview_file_states_service.TILE, str(preview_file.id))]
    )
    result = remote_job.run_job(
        app, config, config_store.get_nomad_tile_job(), params
    )
    probed = preview_file_states_service.probe_file_states(
        preview_file.id, "mp4", files=[preview_file_states_service.TILE]
    )
    preview_file_states_service.record_file_states(
        preview_file.id,
        preview_file_states_service.fail_missing(
            probed, [preview_file_states_service.TILE]
        ),
    )
    return result


def _generate_missing_tile_locally(preview_file):
    """
    Build the tile sheet on this host, one movie at a time. While another
    build runs, give up and forget the attempt: the next 404 queues it
    again instead of piling decodes up on the API cores.
    """
    store = _tile_store()
    # A plain SET NX, not redis-py's Lock: its release runs a Lua script,
    # which the fakeredis the tests run on does not support.
    token = fields.gen_uuid().hex
    if not store.set(
        LOCAL_TILE_BUILD_LOCK_KEY,
        token,
        nx=True,
        ex=int(config.JOB_QUEUE_TIMEOUT),
    ):
        store.delete(_tile_attempt_key(preview_file.id))
        return False
    try:
        movie_path = preview_files_service.retrieve_stored_movie(preview_file)
        if movie_path is None:
            return False
        preview_files_service.generate_tiles(
            file_store, preview_file, movie_path, 1, 1
        )
        return True
    finally:
        # Only release a lock still ours: an expired one may have been
        # taken by another build since.
        if store.get(LOCAL_TILE_BUILD_LOCK_KEY) == token:
            store.delete(LOCAL_TILE_BUILD_LOCK_KEY)


def _tile_store():
    return redis_client.get_client(config.KV_JOB_DB_INDEX)


def _tile_attempt_key(preview_file_id):
    return f"tile-attempt:{preview_file_id}"


def _reset_preview_file_metadata(
    preview_file, preview_file_path, total, index
):
    """
    Recompute the width, height, duration and file size of one preview
    from the file on disk.
    """
    try:
        if preview_file.extension == "mp4":
            width, height = movie.get_movie_size(preview_file_path)
        else:
            width, height = thumbnail_utils.get_dimensions(preview_file_path)
        file_size = os.path.getsize(preview_file_path)
        duration = (
            float(movie.get_movie_duration(preview_file_path))
            if preview_file.extension == "mp4"
            else None
        )
        preview_files_service.update_preview_file_raw(
            preview_file,
            {
                "width": width,
                "height": height,
                "file_size": file_size,
                "duration": duration,
            },
        )
        logger.info(
            f"{index:0{len(str(total))}}/{total} Size information stored for {preview_file.id}.",
        )
    except Exception as e:
        logger.warning(
            f"Failed to store information for preview file {preview_file.id}: {e}.",
        )
