import base64
import logging
import os
import shutil
import tempfile
import zlib
from pathlib import Path
from shutil import copyfile
from zipfile import ZipFile

import orjson as json
from flask import current_app
from slugify import slugify

from zou.app import config
from zou.app.exceptions import BuildJobNotFoundException
from zou.app.models.build_job import BuildJob
from zou.app.models.playlist import Playlist
from zou.app.services import (
    base_service,
    files_service,
    organisation_service,
    persons_service,
    playlists_service,
    preview_files_service,
    shots_service,
    stored_files_service,
    templates_service,
)
from zou.app.stores import config_store, file_store
from zou.app.utils import emails, events, fields, fs, remote_job
from zou.utils import movie

logger = logging.getLogger(__name__)


def retrieve_playlist_tmp_files(preview_files, full=False, tmp_dir=None):
    """
    Copy the files of the given previews into tmp_dir (TMP_DIR if None). With
    full, copy all preview files of the same revision. The caller owns tmp_dir
    and removes it at the end. Return a list of (copy path, file name) tuples.
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
    Copy one preview of a playlist to tmp_dir (TMP_DIR if None), so that ffmpeg
    can concatenate it locally. The name of the copy starts with its index.
    Thus two previews with the same display name keep their own file. Return
    the copy path and the file name.
    """
    if tmp_dir is None:
        tmp_dir = config.TMP_DIR
    # Use the same cache entry as the preview routes, and write it in the same
    # way. If a download stops halfway, it must not leave a truncated file. The
    # next build concatenates such a file as is.
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
    file_name = preview_files_service.get_preview_file_name(preview_file["id"])
    tmp_file_path = os.path.join(tmp_dir, f"{index:04d}_{file_name}")
    copyfile(file_path, tmp_file_path)
    return tmp_file_path, file_name


def _retrieve_playlist_movie(preview_file):
    """
    Return the local path of the movie of the given preview, for the version
    that the normalization settings left in the store. Go to the next version
    only if the absence is confirmed. A transient failure must not build the
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
    Build a zip of all files of the given playlist in the temporary folder.
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
                    # Two entries with the same name: the extraction keeps only
                    # one. Thus the name of the copy contains its index.
                    file_name = os.path.basename(file_path)
                file_names.add(file_name)
                zip.write(file_path, file_name)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return zip_file_path


def build_playlist_movie_file(playlist, job, shots, params, full, remote):
    """
    Build the movie of the given playlist from the movie previews of the given
    shots, locally or with a remote job, and store it. End the build job and
    return it as a dict. If the build fails, raise an exception.
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
                    # Only a local build reads the previews here. The remote
                    # runner gets them itself. If necessary, it uses the other
                    # versions or a placeholder.
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

                    # The concat filter encodes again. It is the fallback of
                    # the demuxer, and the only mode of a full build.
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
            # The worker stops. The build continues in the next worker.
            handed_over = True
            raise
        except Exception as exc:
            app.logger.error(exc)
            success = False

        finally:
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            if not handed_over:
                job = end_build_job(playlist, job, success, message)

    # rq logs this exception and sets the job as failed.
    if not success:
        raise Exception(f"Failure while building playlist {playlist['id']!r}")

    return job


def _run_concatenation(
    playlist, job, tmp_file_paths, movie_file_path, params, mode
):
    """
    Concatenate the downloaded previews into the playlist movie, then store it.
    Return whether it succeeded, and the concatenation message, if there is
    one.
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
    Give the concatenation to a remote Nomad job, and do not run it in the
    process. Then download the stored movie to the local cache and return its
    path.
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

    # Fill the cache that the download route reads, immediately. Write the file
    # to a different location, then rename it. If a download stops, it must not
    # leave a truncated movie in the cache. The route serves such a movie as
    # is.
    exception = fs.download_to_file(
        movie_file_path, file_store.open_movie, "playlists", job["id"]
    )
    if exception is not None:
        raise exception

    return movie_file_path


def start_build_job(playlist):
    """
    Record in the database that a new build is running. Emit an event to tell
    the clients that a new job is running.
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
    Record in the database that a build is finished. Emit an event to tell the
    clients that the build is done. The optional message explains a degraded or
    failed build.

    The job can be deleted while the build runs. In that case, its files were
    removed before the build stored the movie. Thus remove them again here, and
    return an empty dict.
    """
    if success:
        status = "succeeded"
    else:
        status = "failed"

    build_job = BuildJob.get(job["id"])
    if build_job is None:
        current_app.logger.warning(
            f"Build job {job['id']} was deleted while running, "
            "its movie is discarded."
        )
        remove_build_job_files(job)
        return {}

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
    return build_job.serialize()


def build_playlist_job(playlist, job, shots, params, email, full, remote):
    """
    Build the playlist file (concatenate all movie previews). If the build
    succeeds, send the download link by email to the given address. Run this
    function as a job in a job queue.
    """
    # The job dict given to the queue still says "running". Test the status
    # that end_build_job returns. This status is empty if the job was deleted
    # during the build.
    job = build_playlist_movie_file(playlist, job, shots, params, full, remote)

    if job.get("status") == "succeeded":
        from zou.app import app

        with app.app_context():
            person = persons_service.get_person_by_email_raw(email)
            organisation = organisation_service.get_organisation()
            playlist_url = (
                f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
                f"/api/data/playlists/{playlist['id']}/jobs/{job['id']}"
                "/build/mp4"
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
    Build the context name (slug) for the file names of playlist downloads. For
    tvshow projects, add the episode name (or "main pack" / "all assets").
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
    Build the file path of the movie file of the given build job.
    """
    movie_file_name = f"cache-playlists-{build_job['id']}.mp4"
    return os.path.join(config.TMP_DIR, movie_file_name)


def get_playlist_zip_file_path(playlist):
    """
    Build a file path for an archive of the given playlist. Each call gives a
    unique path: concurrent downloads of a playlist each remove their own
    archive after they send it.
    """
    zip_file_name = f"{playlist['id']}-{fields.gen_uuid()}.zip"
    return os.path.join(config.TMP_DIR, zip_file_name)


def get_build_job_raw(build_job_id):
    """
    Return the given build job as an active record.
    """
    return base_service.get_instance(
        BuildJob, build_job_id, BuildJobNotFoundException
    )


def get_build_job(build_job_id):
    """
    Return the given build job as a dict.
    """
    return get_build_job_raw(build_job_id).serialize()


def remove_build_job_files(job_dict):
    """
    Remove the movie of given build job from the cache and the storage.
    Return the path of the cache file.
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
    return movie_file_path


def remove_build_job_impl(playlist, job_dict):
    """
    Remove one build job: its files and its database record. Emit an event. The
    caller gives the serialized job dict. Return the path of the cache file.
    """
    build_job_id = job_dict["id"]
    movie_file_path = remove_build_job_files(job_dict)
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
    Remove the build job from the database, and remove its movie from the cache
    and the storage. Return the path of the cache file. If the job does not
    exist, return None.
    """
    job = BuildJob.get(build_job_id)
    if job is None:
        return None
    return remove_build_job_impl(playlist, job.serialize())


def get_build_jobs_for_project(project_id):
    """
    Return all build_jobs of the given project.
    """
    build_jobs = BuildJob.query.join(Playlist).filter(
        Playlist.project_id == project_id
    )
    return fields.serialize_list(build_jobs)
