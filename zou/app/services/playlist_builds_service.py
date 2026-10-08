import base64
import logging
import orjson as json
import os
import shutil
import tempfile
import zlib
from flask import current_app
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile
from slugify import slugify

from zou.app import config
from zou.app.stores import config_store, file_store
from zou.app.models.build_job import BuildJob
from zou.app.models.playlist import Playlist
from zou.utils import movie
from zou.app.utils import fields, events, fs, remote_job, emails
from zou.app.services import (
    base_service,
    files_service,
    preview_files_service,
    shots_service,
    stored_files_service,
    names_service,
    persons_service,
    templates_service,
    organisation_service,
    playlists_service,
)
from zou.app.exceptions import BuildJobNotFoundException

logger = logging.getLogger(__name__)


def retrieve_playlist_tmp_files(preview_files, full=False, tmp_dir=None):
    """
    Retrieve all files for a given playlist into the temporary folder. The
    copies land in tmp_dir, which the caller owns and removes once done:
    they used to pile up in TMP_DIR and two previews sharing an upload name
    overwrote each other.
    """
    if tmp_dir is None:
        tmp_dir = config.TMP_DIR
    file_paths = []
    for preview_file in preview_files:
        if full:
            preview_file = files_service.get_preview_file(preview_file["id"])
            sub_preview_files = (
                preview_files_service.get_preview_files_for_revision(
                    preview_file["task_id"], preview_file["revision"]
                )
            )
            for preview_file in sub_preview_files:
                tmp_file_path, file_name = retrieve_playlist_tmp_file(
                    preview_file, tmp_dir, len(file_paths)
                )
                file_paths.append((tmp_file_path, file_name))
        else:
            tmp_file_path, file_name = retrieve_playlist_tmp_file(
                preview_file, tmp_dir, len(file_paths)
            )
            file_paths.append((tmp_file_path, file_name))
    return file_paths


def retrieve_playlist_tmp_file(preview_file, tmp_dir=None, index=0):
    """
    Download one preview of a playlist to the temp folder, so ffmpeg can
    concatenate it locally. The copy is prefixed by its index so that two
    previews carrying the same display name keep their own file.
    """
    if tmp_dir is None:
        tmp_dir = config.TMP_DIR
    # Same cache entry as the preview routes, written the same way: a
    # download interrupted halfway must not leave a truncated file that
    # the next build would concatenate as is.
    if preview_file["extension"] == "mp4":
        file_path = _retrieve_playlist_movie(preview_file)
    elif preview_file["extension"] == "png":
        file_path = fs.get_file_path_and_file(
            config,
            file_store.get_local_picture_path,
            file_store.open_picture,
            "original",
            preview_file["id"],
            "png",
        )
    else:
        file_path = fs.get_file_path_and_file(
            config,
            file_store.get_local_file_path,
            file_store.open_file,
            "previews",
            preview_file["id"],
            preview_file["extension"],
        )
    file_name = names_service.get_preview_file_name(preview_file["id"])
    tmp_file_path = os.path.join(tmp_dir, f"{index:04d}_{file_name}")
    copyfile(file_path, tmp_file_path)
    return tmp_file_path, file_name


def _retrieve_playlist_movie(preview_file):
    """
    Local path of the movie of given preview, whichever version the
    normalization settings left in the store. Only a confirmed absence
    moves on to the next version: a transient failure must not build the
    playlist from the low def movie.
    """
    last_error = None
    for prefix in preview_files_service.get_stored_movie_prefixes(
        preview_file
    ):
        try:
            return fs.get_file_path_and_file(
                config,
                file_store.get_local_movie_path,
                file_store.open_movie,
                prefix,
                preview_file["id"],
                "mp4",
            )
        except fs.ConfirmedFileNotFound as error:
            last_error = error
    raise last_error


def build_playlist_zip_file(playlist):
    """
    Build a zip for all files for a given playlist into the temporary folder.
    """
    previews = playlists_service.playlist_previews(playlist["shots"])
    tmp_dir = tempfile.mkdtemp(prefix="playlist-zip-", dir=config.TMP_DIR)
    try:
        tmp_file_paths = retrieve_playlist_tmp_files(
            previews, full=True, tmp_dir=tmp_dir
        )

        zip_file_path = get_playlist_zip_file_path(playlist)
        file_names = set()
        with ZipFile(zip_file_path, "w") as zip:
            for file_path, file_name in tmp_file_paths:
                if file_name in file_names:
                    # Two entries of the same name: the extraction would
                    # keep one. The copy name carries its index.
                    file_name = os.path.basename(file_path)
                file_names.add(file_name)
                zip.write(file_path, file_name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return zip_file_path


def build_playlist_movie_file(playlist, job, shots, params, full, remote):
    """
    Build a movie for all files for a given playlist into the temporary folder.
    """
    success = False
    message = None
    handed_over = False
    from zou.app import app

    with app.app_context():
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(
                prefix="playlist-build-", dir=config.TMP_DIR
            )
            previews = playlists_service.playlist_previews(
                shots, only_movies=True
            )
            movie_file_path = get_playlist_movie_file_path(job)

            if previews:
                if not remote:
                    # Only a local build reads the previews here: the
                    # remote runner fetches them itself, falling back on
                    # the other versions and on a placeholder.
                    tmp_file_paths = retrieve_playlist_tmp_files(
                        previews, tmp_dir=tmp_dir
                    )
                    success = False
                    demuxer_message = None
                    if not full:
                        success, demuxer_message = _run_concatenation(
                            playlist,
                            job,
                            tmp_file_paths,
                            movie_file_path,
                            params,
                            movie.concat_demuxer,
                        )

                    # Try again using concat filter
                    if not success:
                        success, _ = _run_concatenation(
                            playlist,
                            job,
                            tmp_file_paths,
                            movie_file_path,
                            params,
                            movie.concat_filter,
                        )
                        if success and demuxer_message is not None:
                            message = (
                                "The exact concat demuxer rejected the "
                                f"previews ({demuxer_message}). The movie "
                                "was built by the re-encoding concat "
                                "filter instead, its timing can drift "
                                "from the source previews."
                            )
                            app.logger.warning(message)
                else:
                    try:
                        _run_remote_job_build_playlist(
                            app, job, previews, params, movie_file_path, full
                        )
                        success = True
                    except Exception as exc:
                        app.logger.error(exc)
                        success = False

        except remote_job.NomadJobHandedOver:
            # The worker stops: the build goes on in the next one.
            handed_over = True
            raise
        except Exception as exc:
            app.logger.error(exc)
            success = False

        # exception will be logged by rq
        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            if not handed_over:
                job = end_build_job(playlist, job, success, message)

    if not success:
        raise Exception(f"Failure while building playlist {playlist['id']!r}")

    return job


def _run_concatenation(
    playlist, job, tmp_file_paths, movie_file_path, params, mode
):
    """
    Concatenate the downloaded previews into the playlist movie, then
    store it and clean the temporary files up. Return whether it
    succeeded, along with the concatenation message, if any.
    """
    success = False
    message = None
    try:
        result = movie.build_playlist_movie(
            mode, tmp_file_paths, movie_file_path, **params._asdict()
        )
        message = result.get("message")
        if result["success"] and os.path.exists(movie_file_path):
            file_store.add_movie("playlists", job["id"], movie_file_path)
            success = True
        if message:
            from zou.app import app

            with app.app_context():
                app.logger.error(message)
    except Exception:
        from zou.app import app

        with app.app_context():
            app.logger.error(
                "Unable to build playlist %r using %s",
                playlist["id"],
                mode.__qualname__,
                exc_info=1,
            )
    return success, message


def _run_remote_job_build_playlist(
    app, job, previews, params, movie_file_path, full
):
    """
    Hand the concatenation over to a remote worker instead of running it
    in process, when a job queue is configured.
    """
    preview_ids = [
        preview["id"] for preview in previews if preview["extension"] == "mp4"
    ]
    input_bytes = zlib.compress(json.dumps(preview_ids))
    input_string = base64.b64encode(input_bytes).decode("ascii")
    params = {
        "version": "1",
        "output_filename": Path(movie_file_path).name,
        "output_key": file_store.make_key("playlists", job["id"]),
        "input": input_string,
        "width": params.width,
        "height": params.height,
        "fps": params.fps,
        "full": str(full).lower(),
    }
    nomad_job = config_store.get_nomad_playlist_job()
    stored_files_service.record_remote_writes(
        [("movies", "playlists", job["id"])]
    )
    remote_job.run_job(app, config, nomad_job, params)

    # Warm the cache the download route reads, right away. Written aside
    # then renamed: an interrupted download must not leave a truncated
    # movie there, which the route would serve as is.
    exception = fs.download_to_file(
        movie_file_path, file_store.open_movie, "playlists", job["id"]
    )
    if exception is not None:
        raise exception

    return movie_file_path


def start_build_job(playlist):
    """
    Register in database that a new build is running. Emits an event to notify
    clients that a new job is running.
    """
    job = BuildJob.create(
        status="running", job_type="movie", playlist_id=playlist["id"]
    )
    events.emit(
        "build-job:new",
        {
            "build_job_id": str(job.id),
            "playlist_id": playlist["id"],
            "created_at": fields.serialize_value(job.created_at),
        },
        project_id=playlist["project_id"],
    )
    return job.serialize()


def end_build_job(playlist, job, success, message=None):
    """
    Register in database that a build is finished. Emits an event to notify
    clients that the build is done. The optional message explains a
    degraded or failed build.
    """
    if success:
        status = "succeeded"
    else:
        status = "failed"

    build_job = BuildJob.get(job["id"])
    if build_job is not None:
        build_job.end(status=status, message=message)
    events.emit(
        "build-job:update",
        {
            "build_job_id": job["id"],
            "playlist_id": playlist["id"],
            "status": status,
            "message": message,
        },
        project_id=playlist["project_id"],
    )
    if build_job is not None:
        return build_job.serialize()
    else:
        return {}


def build_playlist_job(playlist, job, shots, params, email, full, remote):
    """
    Build playlist file (concatenate all movie previews). This function is
    aimed at being run as a job in a job queue.
    """
    # The job dict handed to the queue still says "running": the status
    # to test is the one end_build_job returns.
    job = build_playlist_movie_file(playlist, job, shots, params, full, remote)

    # Just in case, since rq jobs which encounter an error raise an
    # exception in order to be flagged as failed.
    if job["status"] == "succeeded":
        person = persons_service.get_person_by_email_raw(email)
        organisation = organisation_service.get_organisation()
        playlist_url = (
            f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
            f"/api/data/playlists/{playlist['id']}/jobs/{job['id']}/build/mp4"
        )
        html = f"""<p>Hello {person.first_name},</p>
<p>Your playlist {playlist["name"]} build is available:
</p>
<p class="cta">
<a href="{playlist_url}">Download Playlist Build (.mp4)</a>
</p>
"""

        subject = f"{organisation['name']} - Kitsu: playlist download"
        title = "Playlist Download"
        email_html_body = templates_service.generate_html_body(title, html)
        emails.send_email(subject, email_html_body, email)


def get_playlist_download_context_name(project, playlist):
    """
    Build the context name (slug) for playlist download filenames.
    For tvshow projects, appends episode name (or "main pack" / "all assets").
    """
    context_name = slugify(project["name"], separator="_")
    if project.get("production_type") == "tvshow":
        episode_id = playlist.get("episode_id")
        if episode_id is not None:
            episode = shots_service.get_episode(episode_id)
            episode_name = episode["name"]
        elif playlist.get("is_for_all"):
            episode_name = (
                "all assets"
                if playlist.get("for_entity") == "asset"
                else "all shots"
            )
        else:
            episode_name = "main pack"
        context_name += f"_{slugify(episode_name, separator='_')}"
    return context_name


def get_playlist_movie_file_path(build_job):
    """
    Build file path for the movie file matching given playlist.
    """
    movie_file_name = f"cache-playlists-{build_job['id']}.mp4"
    return os.path.join(config.TMP_DIR, movie_file_name)


def get_playlist_zip_file_path(playlist):
    """
    Build a file path for an archive of given playlist. Unique per call:
    concurrent downloads of a playlist each remove their own archive once
    sent.
    """
    zip_file_name = f"{playlist['id']}-{fields.gen_uuid()}.zip"
    return os.path.join(config.TMP_DIR, zip_file_name)


def get_build_job_raw(build_job_id):
    """
    Return given build job as active record.
    """
    return base_service.get_instance(
        BuildJob, build_job_id, BuildJobNotFoundException
    )


def get_build_job(build_job_id):
    """
    Return given build job as a dict.
    """
    return get_build_job_raw(build_job_id).serialize()


def remove_build_job_impl(playlist, job_dict):
    """
    Remove one build job (file + DB record + event). Caller must pass
    serialized job dict to avoid re-fetching when deleting multiple jobs.
    """
    build_job_id = job_dict["id"]
    movie_file_path = get_playlist_movie_file_path(job_dict)
    if os.path.exists(movie_file_path):
        os.remove(movie_file_path)
    try:
        file_store.remove_movie("playlists", build_job_id)
    except Exception:
        current_app.logger.error(
            f"Playlist file can't be deleted: {build_job_id}"
        )
    job = BuildJob.get(build_job_id)
    if job is not None:
        job.delete()
    events.emit(
        "build-job:delete",
        {"build_job_id": build_job_id, "playlist_id": playlist["id"]},
        project_id=playlist["project_id"],
    )
    return movie_file_path


def remove_build_job(playlist, build_job_id):
    """
    Remove build job from database and remove related temporary file from
    hard drive.
    """
    job = BuildJob.get(build_job_id)
    if job is None:
        return None
    return remove_build_job_impl(playlist, job.serialize())


def get_build_jobs_for_project(project_id):
    """
    Return all build_jobs for given project.
    """
    build_jobs = BuildJob.query.join(Playlist).filter(
        Playlist.project_id == project_id
    )
    return fields.serialize_list(build_jobs)
