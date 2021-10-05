import os
import re
import time

import ffmpeg

from zou.app import config
from zou.app.stores import file_store

from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.models.task import Task
from zou.app.services import names_service, files_service
from zou.utils import movie
from zou.app.utils import (
    events,
    fields,
    remote_job,
    thumbnail as thumbnail_utils,
)
from zou.app.services.exception import PreviewFileNotFoundException
from zou.app.utils import fs


def get_preview_file_dimensions(project):
    """
    Return dimensions set at project level or default dimensions if the
    dimensions are not set.
    """
    resolution = project["resolution"]
    height = 1080
    width = None
    if resolution is not None and bool(re.match(r"\d*x\d*", resolution)):
        [width, height] = resolution.split("x")
        width = int(width)
        height = int(height)
    return (width, height)


def get_preview_file_fps(project):
    """
    Return fps set at project level or default fps if the dimensions are not
    set.
    """
    fps = "24.00"
    if project["fps"] is not None:
        fps = "%.2f" % float(project["fps"].replace(",", "."))
    return fps


def get_project_from_preview_file(preview_file_id):
    """
    Get project dict of related preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    task = Task.get(preview_file.task_id)
    project = Project.get(task.project_id)
    return project.serialize()


def update_preview_file(preview_file_id, data):
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    preview_file.update(data)
    files_service.clear_preview_file_cache(preview_file_id)
    task = Task.get(preview_file.task_id)
    events.emit(
        "preview-file:update",
        {"preview_file_id": preview_file_id},
        project_id=str(task.project_id),
    )
    return preview_file.serialize()


def set_preview_file_as_broken(preview_file_id):
    """
    Mark given preview file as broken.
    """
    return update_preview_file(preview_file_id, {"status": "broken"})


def set_preview_file_as_ready(preview_file_id):
    """
    Mark given preview file as ready.
    """
    return update_preview_file(preview_file_id, {"status": "ready"})


def prepare_and_store_movie(
    preview_file_id,
    uploaded_movie_path,
    normalize=True
):
    """
    Prepare movie preview, normalize the movie as a .mp4, build the thumbnails
    and store the files.
    """
    from zou.app import app as current_app

    with current_app.app_context():
        try:
            project = get_project_from_preview_file(preview_file_id)
        except PreviewFileNotFoundException:
            time.sleep(2)
            try:
                project = get_project_from_preview_file(preview_file_id)
            except PreviewFileNotFoundException:
                current_app.logger.error(
                    "Data is missing from database", exc_info=1
                )
                time.sleep(2)
                preview_file = set_preview_file_as_broken(preview_file_id)
                return preview_file

        fps = get_preview_file_fps(project)
        (width, height) = get_preview_file_dimensions(project)

        if normalize:
            # Build movie
            current_app.logger.info("start normalization")
            try:
                if (
                    config.ENABLE_JOB_QUEUE_REMOTE
                    and len(config.JOB_QUEUE_NOMAD_NORMALIZE_JOB) > 0
                ):
                    file_store.add_movie(
                        "source", preview_file_id, uploaded_movie_path
                    )
                    result = _run_remote_normalize_movie(
                        current_app, preview_file_id, fps, width, height
                    )
                    if result is True:
                        err = None
                    else:
                        err = result

                    normalized_movie_path = fs.get_file_path_and_file(
                        config,
                        file_store.get_local_movie_path,
                        file_store.open_movie,
                        "previews",
                        preview_file_id,
                        ".mp4",
                    )
                else:
                    (
                        normalized_movie_path,
                        normalized_movie_low_path,
                        err,
                    ) = movie.normalize_movie(
                        uploaded_movie_path, fps=fps, width=width, height=height
                    )
                    file_store.add_movie(
                        "previews", preview_file_id, normalized_movie_path
                    )
                    file_store.add_movie(
                        "lowdef", preview_file_id, normalized_movie_low_path
                    )
                if err:
                    current_app.logger.error(
                        "Fail to normalize: %s" % uploaded_movie_path
                    )
                    current_app.logger.error(err)

                current_app.logger.info(
                    "file normalized %s" % normalized_movie_path
                )
                current_app.logger.info("file stored")
            except Exception as exc:
                if isinstance(exc, ffmpeg.Error):
                    current_app.logger.error(exc.stderr)
                current_app.logger.error("failed", exc_info=1)
                preview_file = set_preview_file_as_broken(preview_file_id)
                return preview_file
        else:
            file_store.add_movie(
                "previews", preview_file_id, uploaded_movie_path
            )
            file_store.add_movie(
                "lowdef", preview_file_id, uploaded_movie_path
            )
            normalized_movie_path = uploaded_movie_path

        # Build thumbnails
        size = movie.get_movie_size(normalized_movie_path)
        original_picture_path = movie.generate_thumbnail(normalized_movie_path)
        thumbnail_utils.resize(original_picture_path, size)
        save_variants(preview_file_id, original_picture_path)
        file_size = os.path.getsize(normalized_movie_path)
        current_app.logger.info("thumbnail created %s" % original_picture_path)

        # Remove files and update status
        os.remove(uploaded_movie_path)
        if normalize:
            os.remove(normalized_movie_path)
        preview_file = update_preview_file(
            preview_file_id, {"status": "ready", "file_size": file_size}
        )
        return preview_file


def _run_remote_normalize_movie(app, preview_file_id, fps, width, height):
    bucket_prefix = config.FS_BUCKET_PREFIX
    params = {
        "version": "1",
        "bucket_prefix": bucket_prefix,
        "preview_file_id": preview_file_id,
        "width": width,
        "height": height,
        "fps": fps,
    }
    nomad_job = app.config["JOB_QUEUE_NOMAD_NORMALIZE_JOB"]
    result = remote_job.run_job(app, config, nomad_job, params)
    return result


def save_variants(preview_file_id, original_picture_path):
    """
    Build variants of a picture file and save them in the main storage.
    """
    variants = thumbnail_utils.generate_preview_variants(
        original_picture_path, preview_file_id
    )
    variants.append(("original", original_picture_path))
    for (name, path) in variants:
        file_store.add_picture(name, preview_file_id, path)
        os.remove(path)

    return []  # variants


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
        for (i, preview) in enumerate(tmp_list):
            preview.update({"position": i + 1})
    return PreviewFile.serialize_list(preview_files)


def get_preview_files_for_revision(task_id, revision):
    """
    Get all preview files for given task and revision.
    """
    preview_files = PreviewFile.query.filter_by(
        task_id=task_id, revision=revision
    ).order_by(PreviewFile.position)
    return fields.serialize_models(preview_files)


def update_preview_file_annotations(
    person_id,
    project_id,
    preview_file_id,
    additions=[],
    updates=[],
    deletions=[],
):
    """
    Update annotations for given preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    previous_annotations = preview_file.annotations or []
    annotations = _apply_annotation_additions(previous_annotations, additions)
    annotations = _apply_annotation_updates(annotations, updates)
    annotations = _apply_annotation_deletions(annotations, deletions)
    preview_file.update({"annotations": []})
    preview_file.update({"annotations": annotations})
    files_service.clear_preview_file_cache(preview_file_id)
    preview_file = files_service.get_preview_file(preview_file_id)
    events.emit(
        "preview-file:annotation-update",
        {
            "preview_file_id": preview_file_id,
            "person_id": person_id,
            "updated_at": preview_file["updated_at"],
        },
        project_id=project_id,
    )
    return preview_file


def _apply_annotation_additions(previous_annotations, new_annotations):
    annotations = list(previous_annotations)
    annotation_map = _get_annotation_time_map(annotations)

    for new_annotation in new_annotations:
        previous_annotation = annotation_map.get(new_annotation["time"], None)
        if previous_annotation is None:
            new_objects = new_annotation.get("drawing", {}).get("objects", [])
            for new_object in new_objects:
                if "id" not in new_object or len(new_object["id"]) == 0:
                    new_object["id"] = str(fields.gen_uuid())
            annotations.append(new_annotation)
        else:
            previous_objects = previous_annotation.get("drawing", {}).get(
                "objects", []
            )
            new_objects = new_annotation.get("drawing", {}).get("objects", [])
            previous_annotation["drawing"]["objects"] = _get_new_annotations(
                previous_objects, new_objects
            )
    return annotations


def _get_new_annotations(previous_objects, new_objects):
    result = list(previous_objects)
    previous_map = {}
    for previous_object in result:
        if "id" not in previous_object or len(previous_object["id"]) == 0:
            previous_object["id"] = str(fields.gen_uuid())
        previous_map[previous_object["id"]] = True

    for new_object in new_objects:
        object_id = new_object.get("id", "")
        if object_id not in previous_map:
            result.append(new_object)
    return result


def _apply_annotation_updates(annotations, updates):
    annotation_map = _get_annotation_time_map(annotations)
    for update in updates:
        time = update["time"]
        if time in annotation_map:
            result = []
            previous_object_map = {}
            update_map = {}
            annotation = annotation_map[time]

            previous_objects = annotation.get("drawing", {}).get("objects", [])
            for previous_object in previous_objects:
                previous_object_map[previous_object["id"]] = previous_object

            updated_objects = update.get("drawing", {}).get("objects", [])
            for updated_object in updated_objects:
                update_map[updated_object["id"]] = update

            result = [
                previous_object
                for previous_object in previous_objects
                if previous_object["id"] not in update_map
            ]
            for updated_object in updated_objects:
                if updated_object["id"] in previous_object_map:
                    result.append(updated_object)
            annotation["drawing"]["objects"] = result
    return annotations


def _apply_annotation_deletions(annotations, deletions):
    annotation_map = _get_annotation_time_map(annotations)

    for deletion in deletions:
        if deletion["time"] in annotation_map:
            annotation = annotation_map[deletion["time"]]
            deleted_object_ids = deletion.get("objects", [])
            previous_objects = annotation.get("drawing", {}).get("objects", [])
            annotation.get("drawing", {})["objects"] = [
                previous_object
                for previous_object in previous_objects
                if previous_object.get("id", "") not in deleted_object_ids
            ]

    return _clear_empty_annotations(annotations)


def _get_annotation_time_map(annotations):
    annotation_map = {}
    for annotation in annotations:
        annotation_map[annotation["time"]] = annotation
    return annotation_map


def _clear_empty_annotations(annotations):
    return [
        annotation
        for annotation in annotations
        if len(annotation.get("drawing", {}).get("objects", [])) > 0
    ]


def get_running_preview_files():
    """
    Return preview files for all productions with status equals to broken
    or processing.
    """
    entries = (
        PreviewFile.query.join(Task)
        .join(Project)
        .join(ProjectStatus)
        .filter(ProjectStatus.name.in_(("Active", "open", "Open")))
        .filter(PreviewFile.status.in_(("broken", "processing")))
        .add_columns(Task.project_id, Task.task_type_id, Task.entity_id)
        .order_by(PreviewFile.created_at.desc())
    )

    results = []
    for (preview_file, project_id, task_type_id, entity_id) in entries:
        result = preview_file.serialize()
        result["project_id"] = fields.serialize_value(project_id)
        result["task_type_id"] = fields.serialize_value(task_type_id)
        (result["full_entity_name"], _) = names_service.get_full_entity_name(
            entity_id
        )
        results.append(result)
    return results
