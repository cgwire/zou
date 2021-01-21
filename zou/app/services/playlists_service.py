import os
from operator import itemgetter
from slugify import slugify

from shutil import copyfile
from zipfile import ZipFile

from flask import current_app
from flask_mail import Message
from sqlalchemy import or_

from zou.app import config
from zou.app.stores import file_store

from zou.app.models.build_job import BuildJob
from zou.app.models.playlist import Playlist
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.utils import fields, movie_utils, events
from zou.app.utils import query as query_utils

from zou.app.services import (
    assets_service,
    base_service,
    entities_service,
    files_service,
    projects_service,
    shots_service,
    tasks_service,
    names_service,
)

from zou.app.services.exception import (
    BuildJobNotFoundException,
    PlaylistNotFoundException,
)


def all_playlists_for_project(project_id, for_client=False):
    """
    Return all playlists created for given project.
    """
    result = []
    if for_client:
        playlists = Playlist.get_all_by(project_id=project_id, for_client=True)
    else:
        playlists = Playlist.get_all_by(project_id=project_id)
    for playlist in playlists:
        playlist_dict = build_playlist_dict(playlist)
        result.append(playlist_dict)
    return result


def all_playlists_for_episode(project_id, episode_id, for_client=False):
    """
    Return all playlists created for given episode.
    """
    result = []
    query = Playlist.query
    if for_client:
        query = query.filter(Playlist.for_client == True)

    if episode_id == "main":
        query = query \
            .filter(Playlist.episode_id == None) \
            .filter(Playlist.project_id == project_id) \
            .filter(
                or_(
                    Playlist.is_for_all == None,
                    Playlist.is_for_all == False
                )
            )
    elif episode_id == "all":
        query = query \
            .filter(Playlist.episode_id == None) \
            .filter(Playlist.project_id == project_id) \
            .filter(Playlist.is_for_all == True)
    else:
        query = query.filter(Playlist.episode_id == episode_id)

    playlists = query.all()
    for playlist in playlists:
        playlist_dict = build_playlist_dict(playlist)
        result.append(playlist_dict)
    return result


def build_playlist_dict(playlist):
    first_shot_preview_file_id = get_first_shot_preview_file_id(playlist)
    updated_at = fields.serialize_value(playlist.updated_at)
    playlist.shots = []
    playlist_dict = fields.serialize_value(playlist)
    del playlist_dict["shots"]
    playlist_dict["updated_at"] = updated_at
    if first_shot_preview_file_id is not None:
        playlist_dict["first_preview_file_id"] = first_shot_preview_file_id
    if playlist.for_entity is None:
        playlist_dict["for_entity"] = "shot"
    return playlist_dict


def get_first_shot_preview_file_id(playlist):
    first_shot_preview_file_id = None
    if playlist.shots is not None \
       and len(playlist.shots) > 0 \
       and type(playlist.shots) == list \
       and "preview_file_id" in playlist.shots[0]:
        first_shot_preview_file_id = playlist.shots[0]["preview_file_id"]
    return first_shot_preview_file_id


def get_playlist_with_preview_file_revisions(playlist_id):
    """
    Return given playlist. Shot list is augmented with all previews available
    for a given shot.
    """
    playlist = get_playlist_raw(playlist_id)
    playlist_dict = playlist.serialize()
    playlist_dict = _add_build_job_infos_to_playlist_dict(
        playlist,
        playlist_dict
    )

    if playlist_dict["shots"] is None:
        playlist_dict["shots"] = []
    (playlist_dict, preview_file_map) = set_preview_files_for_entities(
        playlist_dict
    )

    for shot in playlist_dict["shots"]:
        try:
            preview_file = preview_file_map.get(shot["preview_file_id"], None)
            if preview_file is not None:
                shot["preview_file_id"] = preview_file["id"]
                shot["preview_file_extension"] = preview_file["extension"]
                shot["preview_file_status"] = preview_file["status"]
                shot["preview_file_annotations"] = preview_file["annotations"]
                shot["preview_file_task_id"] = preview_file["task_id"]
                shot["preview_file_previews"] = preview_file["previews"]
            else:
                del shot["preview_file_id"]
        except Exception as e:
            print(e)
    return playlist_dict


def _add_build_job_infos_to_playlist_dict(playlist, playlist_dict):
    playlist_dict["build_jobs"] = []
    for build_job in reversed(playlist.build_jobs):
        playlist_dict["build_jobs"].append(build_job.present())
    return playlist_dict


def set_preview_files_for_entities(playlist_dict):
    """
    """
    entity_ids = []
    for entity in playlist_dict["shots"]:
        if "id" not in entity:
            entity_id = entity.get("shot_id", entity.get("entity_id", None))
            if entity_id is not None:
                entity_ids.append(entity_id)
                entity["id"] = entity_id
        else:
            entity_ids.append(entity["id"])
    previews = {}
    preview_file_map = {}

    preview_files = (
        PreviewFile.query
        .join(Task)
        .join(TaskType)
        .filter(Task.entity_id.in_(entity_ids))
        .order_by(TaskType.priority.desc())
        .order_by(TaskType.name)
        .order_by(PreviewFile.revision.desc())
        .order_by(PreviewFile.created_at)
        .add_column(Task.task_type_id)
        .add_column(Task.entity_id)
        .all()
    )

    is_pictures = False
    for (preview_file, task_type_id, entity_id) in preview_files:
        entity_id = str(entity_id)
        task_type_id = str(task_type_id)
        if entity_id not in previews:
            previews[entity_id] = {}

        if task_type_id not in previews[entity_id]:
            previews[entity_id][task_type_id] = []

        if preview_file.extension == "png":
            is_pictures = True

        task_id = str(preview_file.task_id)
        preview_file_id = str(preview_file.id)

        light_preview_file = {
            "id": preview_file_id,
            "revision": preview_file.revision,
            "extension": preview_file.extension,
            "status": str(preview_file.status),
            "annotations": preview_file.annotations,
            "created_at": fields.serialize_value(preview_file.created_at),
            "task_id": task_id,
        }  # Do not add too much field to avoid building too big responses
        previews[entity_id][task_type_id].append(light_preview_file)
        preview_file_map[preview_file_id] = light_preview_file

    if is_pictures:
        for entity_id in previews.keys():
            for task_type_id in previews[entity_id].keys():
                previews[entity_id][task_type_id] = mix_preview_file_revisions(
                    previews[entity_id][task_type_id]
                )

    for entity in playlist_dict["shots"]:
        if str(entity["id"]) in previews:
            entity["preview_files"] = previews[str(entity["id"])]
        else:
            entity["preview_files"] = []

    return (fields.serialize_value(playlist_dict), preview_file_map)


def get_preview_files_for_entity(entity_id):
    """
    Get all preview files available for given shot.
    """
    previews = {}
    query = (
        Task.query
        .filter_by(entity_id=entity_id)
        .add_columns(
            PreviewFile.id,
            PreviewFile.revision,
            PreviewFile.position,
            PreviewFile.original_name,
            PreviewFile.extension,
            PreviewFile.status,
            PreviewFile.annotations,
            PreviewFile.created_at,
            PreviewFile.task_id
        )
        .join(PreviewFile)
        .join(TaskType)
        .order_by(TaskType.priority.desc())
        .order_by(TaskType.name)
        .order_by(PreviewFile.revision.desc())
        .order_by(PreviewFile.created_at)
    )

    task_previews = {}
    for (
        task,
        preview_file_id,
        preview_file_revision,
        preview_file_position,
        preview_file_original_name,
        preview_file_extension,
        preview_file_status,
        preview_file_annotations,
        preview_file_created_at,
        preview_file_task_id
    ) in query.all():
        task_id = str(task.id)
        if task_id not in task_previews:
            task_previews[task_id] = []
        task_previews[task_id].append(fields.serialize_dict({
            "id": preview_file_id,
            "revision": preview_file_revision,
            "position": preview_file_position,
            "original_name": preview_file_original_name,
            "extension": preview_file_extension,
            "status": preview_file_status,
            "annotations": preview_file_annotations,
            "created_at": preview_file_created_at,
            "task_id": task_id,
            "task_type_id": str(task.task_type_id),
        }))

    for task_id in task_previews.keys():
        preview_files = task_previews[task_id]
        task_type_id = task_previews[task_id][0]["task_type_id"]

        if len(preview_files) > 0:
            preview_files = mix_preview_file_revisions(preview_files)
            previews[task_type_id] = [
                {
                    "id": preview_file["id"],
                    "revision": preview_file["revision"],
                    "original_name": preview_file["original_name"],
                    "extension": preview_file["extension"],
                    "status": preview_file["status"],
                    "annotations": preview_file["annotations"],
                    "previews": preview_file["previews"],
                    "created_at": preview_file["created_at"],
                    "task_id": preview_file["task_id"]
                }
                for preview_file in preview_files
            ]  # Do not add too much field to avoid building too big responses
    return previews


def mix_preview_file_revisions(preview_files):
    """
    The goal here is to group preview files with same revision in a single
    preview file, which encapsulates other preview_files.
    """
    revision_map = {}
    result = []
    for preview_file in preview_files:
        revision = preview_file["revision"]
        if revision not in revision_map:
            preview_file["previews"] = []
            revision_map[revision] = preview_file
            result.append(preview_file)
        else:
            parent_preview_file = revision_map[revision]
            parent_preview_file["previews"].append(preview_file)
    return result


def get_playlist_raw(playlist_id):
    """
    Return given playlist as active record.
    """
    return base_service.get_instance(
        Playlist, playlist_id, PlaylistNotFoundException
    )


def get_playlist(playlist_id):
    """
    Return given playlist as a dict.
    """
    return get_playlist_raw(playlist_id).serialize()


def retrieve_playlist_tmp_files(playlist, only_movies=False):
    """
    Retrieve all files for a given playlist into the temporary folder.
    """
    preview_files = []
    for entity in playlist["shots"]:
        if (
            "preview_file_id" in entity and
            entity["preview_file_id"] is not None and
            len(entity["preview_file_id"]) > 0
        ):
            preview_file = files_service.get_preview_file(
                entity["preview_file_id"]
            )
            if preview_file is not None and (
                (only_movies and preview_file["extension"] == "mp4") or
                not only_movies
            ):
                preview_files.append(preview_file)

    file_paths = []
    for preview_file in preview_files:
        prefix = "original"
        if preview_file["extension"] == "mp4":
            get_path_func = file_store.get_local_movie_path
            open_func = file_store.open_movie
            prefix = "previews"
        elif preview_file["extension"] == "png":
            get_path_func = file_store.get_local_picture_path
            open_func = file_store.open_picture
        else:
            get_path_func = file_store.get_local_file_path
            open_func = file_store.open_file

        if config.FS_BACKEND == "local":
            file_path = get_path_func(
                prefix, preview_file["id"]
            )
        else:
            file_path = os.path.join(
                config.TMP_DIR,
                "cache-previews-%s.%s" % (
                    preview_file["id"],
                    preview_file["extension"]
                ),
            )
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                with open(file_path, "wb") as tmp_file:
                    for chunk in open_func(prefix, preview_file["id"]):
                        tmp_file.write(chunk)

        file_name = names_service.get_preview_file_name(preview_file["id"])
        tmp_file_path = os.path.join(config.TMP_DIR, file_name)
        copyfile(file_path, tmp_file_path)
        file_paths.append((tmp_file_path, file_name))
    return file_paths


def build_playlist_zip_file(playlist):
    """
    Build a zip for all files for a given playlist into the temporary folder.
    """
    tmp_file_paths = retrieve_playlist_tmp_files(playlist)
    zip_file_path = get_playlist_zip_file_path(playlist)
    if os.path.exists(zip_file_path):
        os.remove(zip_file_path)
    with ZipFile(zip_file_path, "w") as zip:
        for file_path, file_name in tmp_file_paths:
            zip.write(file_path, file_name)
    return zip_file_path


def build_playlist_movie_file(playlist, app=None):
    """
    Build a movie for all files for a given playlist into the temporary folder.
    """
    job = start_build_job(playlist)
    project = projects_service.get_project(playlist["project_id"])
    tmp_file_paths = retrieve_playlist_tmp_files(playlist, only_movies=True)
    movie_file_path = get_playlist_movie_file_path(playlist, job)
    (width, height) = shots_service.get_preview_dimensions(project)
    fps = shots_service.get_preview_fps(project)

    result = movie_utils.build_playlist_movie(
        tmp_file_paths, movie_file_path, width, height, fps
    )
    if result["success"] == True:
        if os.path.exists(movie_file_path):
            file_store.add_movie("playlists", job["id"], movie_file_path)
        else:
            if app is not None:
                current_app.logger.error("No playlist was created")
            result["success"] = False
            result["message"] = "No playlist was created"

    elif app is not None:
        current_app.logger.error(result["message"])
    end_build_job(playlist, job, result)
    return job


def start_build_job(playlist):
    """
    clients that a new job is running.
    Register in database that a new build is running. Emits an event to notify
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
        project_id=playlist["project_id"]
    )
    return job.serialize()


def end_build_job(playlist, job, result):
    """
    Register in database that a build is finished. Emits an event to notify
    clients that the build is done.
    """
    build_job = BuildJob.get(job["id"])
    build_job.end()
    status = "succeeded"
    if not result["success"]:
        status = "failed"
    events.emit(
        "build-job:update",
        {
            "build_job_id": str(build_job.id),
            "playlist_id": playlist["id"],
            "status": status,
        },
        project_id=playlist["project_id"]
    )
    return build_job.serialize()


def build_playlist_job(playlist, email):
    """
    Build playlist file (concatenate all mnovie previews). This function is
    aimed at being runned as a job in a job queue.
    """
    from zou.app import app, mail

    with app.app_context():
        job = None
        try:
            job = build_playlist_movie_file(playlist)
        except:
            if job is not None:
                end_build_job(playlist, job)
            raise

        message_text = """
Your playlist %s is available at:
https://%s/api/data/playlists/%s/jobs/%s/build/mp4
""" % (
            playlist["name"],
            config.DOMAIN_NAME,
            playlist["id"],
            job["id"],
        )
        message = Message(
            body=message_text,
            subject="CGWire playlist download",
            recipients=[email],
        )
        mail.send(message)


def get_playlist_file_name(playlist):
    """
    Build file name for the movie file matching given playlist.
    """
    project = projects_service.get_project(playlist["project_id"])
    attachment_filename = "%s_%s" % (
        slugify(project["name"]),
        slugify(playlist["name"]),
    )
    return slugify(attachment_filename)


def get_playlist_movie_file_path(playlist, build_job):
    """
    Build file path for the movie file matching given playlist.
    """
    movie_file_name = "cache-playlists-%s.mp4" % build_job["id"]
    return os.path.join(config.TMP_DIR, movie_file_name)


def get_playlist_zip_file_path(playlist):
    """
    Build file path for the archive file matching given playlist.
    """
    zip_file_name = "%s.zip" % playlist["id"]
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


def remove_playlist(playlist_id):
    """
    Remove given playlist from database (and delete related build jobs).
    """
    playlist = get_playlist_raw(playlist_id)
    playlist_dict = playlist.serialize()
    query = BuildJob.query.filter_by(playlist_id=playlist_id)
    for job in query.all():
        remove_build_job(playlist_dict, job.id)
    playlist.delete()
    events.emit(
        "playlist:delete",
        {"playlist_id": playlist_dict["id"]},
        project_id=playlist_dict["project_id"]
    )
    return playlist_dict


def remove_build_job(playlist, build_job_id):
    """
    Remove build job from database and remove related temporary file from
    hard drive.
    """
    job = BuildJob.get(build_job_id)
    movie_file_path = get_playlist_movie_file_path(playlist, job.serialize())
    if os.path.exists(movie_file_path):
        os.remove(movie_file_path)
    try:
        file_store.remove_movie("playlists", build_job_id)
    except:
        current_app.logger.error(
            "Playlist file can't be deleted: %s" % build_job_id
        )
    job.delete()
    events.emit(
        "build-job:delete",
        {"build_job_id": build_job_id, "playlist_id": playlist["id"]},
        project_id=playlist["project_id"]
    )
    return movie_file_path


def get_build_jobs_for_project(project_id):
    """
    Return all build_jobs for given project.
    """
    build_jobs = BuildJob.query.join(Playlist).filter(
        Playlist.project_id == project_id
    )
    return fields.serialize_list(build_jobs)


def get_playlists_for_project(project_id, page=0):
    """
    Return all time spents for given project.
    """
    query = Playlist.query.filter(Playlist.project_id == project_id)
    return query_utils.get_paginated_results(query, page, relations=True)


def generate_temp_playlist(task_ids):
    """
    Generate the data structure of a playlist for a given task list. It doesn't
    persist anything. The goal is to build a temporary playlist used to see
    a quick preview of several shots.
    """
    entities = []
    for task_id in task_ids:
        entity = generate_playlisted_entity_from_task(task_id)
        entities.append(entity)
    if len(entities) > 0:
        if "sequence_name" in entities[0]:
            return sorted(entities, key=itemgetter('sequence_name', 'name'))
        else:
            return sorted(entities, key=itemgetter('asset_type_name', 'name'))
    else:
        return []


def generate_playlisted_entity_from_task(task_id):
    """
    Generate the data structure of a playlisted shot for a given task. It
    doesn't persist anything.
    """
    task = tasks_service.get_task(task_id)
    entity = entities_service.get_entity(task["entity_id"])
    if shots_service.is_shot(entity):
        playlisted_entity = get_base_shot_for_playlist(entity, task_id)
    else:
        playlisted_entity = get_base_asset_for_playlist(entity, task_id)

    task_type_id = task["task_type_id"]
    preview_files = get_preview_files_for_entity(entity["id"])
    if task_type_id in preview_files and len(preview_files[task_type_id]) > 0:
        preview_file = preview_files[task_type_id][0]
        playlisted_entity.update({
            "preview_file_id": preview_file["id"],
            "preview_file_extension": preview_file["extension"],
            "preview_file_status": preview_file["status"],
            "preview_file_annotations": preview_file["annotations"],
            "preview_file_previews": preview_file["previews"]
        })
    playlisted_entity["preview_files"] = preview_files
    return playlisted_entity


def get_base_shot_for_playlist(entity, task_id):
    shot = shots_service.get_shot(entity["id"])
    sequence = shots_service.get_sequence(shot["parent_id"])
    playlisted_entity = {
        "id": shot["id"],
        "name": shot["name"],
        "preview_file_task_id": task_id,
        "sequence_id": sequence["id"],
        "sequence_name": sequence["name"],
        "parent_name": sequence["name"]
    }
    return playlisted_entity


def get_base_asset_for_playlist(entity, task_id):
    asset = assets_service.get_asset(entity["id"])
    asset_type = assets_service.get_asset_type(asset["entity_type_id"])
    playlisted_entity = {
        "id": asset["id"],
        "name": asset["name"],
        "preview_file_task_id": task_id,
        "asset_type_id": asset_type["id"],
        "asset_type_name": asset_type["name"],
        "parent_name": asset_type["name"]
    }
    return playlisted_entity


def get_preview_files_for_task(task_id):
    """
    Return all preview file active records for given task.
    """
    preview_files = (
        PreviewFile.query.filter_by(task_id=task_id)
        .order_by(PreviewFile.revision.desc())
        .all()
    )
    return _get_playlist_preview_file_list(preview_files)


def _get_playlist_preview_file_list(preview_files):
    """
    Turn preview file active records into preview file dict that match the
    playlist data structure.
    """
    return [
        {
            "id": str(preview_file.id),
            "revision": preview_file.revision,
            "extension": preview_file.extension,
            "status": str(preview_file.status),
            "annotations": preview_file.annotations,
            "created_at": fields.serialize_value(preview_file.created_at),
            "task_id": str(preview_file.task_id),
        }
        for preview_file in preview_files
    ]
