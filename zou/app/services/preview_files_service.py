import os
import re

import ffmpeg

from zou.app.stores import file_store

from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import files_service
from zou.app.utils import events, fields, thumbnail as thumbnail_utils
from zou.utils import movie


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


def prepare_and_store_movie(preview_file_id, uploaded_movie_path):
    """
    Prepare movie preview, normalize the movie as a .mp4, build the thumbnails
    and store the files.
    """
    from zou.app import app as current_app

    with current_app.app_context():
        project = get_project_from_preview_file(preview_file_id)
        fps = get_preview_file_fps(project)
        (width, height) = get_preview_file_dimensions(project)

        # Build movie
        current_app.logger.info("start normalization")
        try:
            (
                normalized_movie_path,
                normalized_movie_low_path,
                err,
            ) = movie.normalize_movie(
                uploaded_movie_path, fps=fps, width=width, height=height
            )

            if err:
                current_app.logger.error(
                    "Fail to add silent audiotrack to: %s" % uploaded_movie_path
                )
                current_app.logger.error(err)

            current_app.logger.info(
                "file normalized %s" % normalized_movie_path
            )
            file_store.add_movie(
                "previews", preview_file_id, normalized_movie_path
            )
            file_store.add_movie(
                "lowdef", preview_file_id, normalized_movie_low_path
            )
            current_app.logger.info("file stored")
        except Exception as exc:
            if isinstance(exc, ffmpeg.Error):
                current_app.logger.error(exc.stderr)
            current_app.logger.error("failed", exc_info=1)
            preview_file = set_preview_file_as_broken(preview_file_id)
            return preview_file

        # Build thumbnails
        size = movie.get_movie_size(normalized_movie_path)
        original_picture_path = movie.generate_thumbnail(normalized_movie_path)
        tile_picture_path = movie.generate_tile(normalized_movie_path)
        thumbnail_utils.resize(original_picture_path, size)
        save_variants(preview_file_id, original_picture_path)
        file_size = os.path.getsize(normalized_movie_path)
        current_app.logger.info("thumbnail created %s" % original_picture_path)

        # Remove files and update status
        os.remove(uploaded_movie_path)
        os.remove(normalized_movie_path)
        preview_file = update_preview_file(
            preview_file_id, {"status": "ready", "file_size": file_size}
        )
        return preview_file


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
    preview_files = (
        PreviewFile.query
        .filter_by(task_id=task_id, revision=revision)
        .order_by(PreviewFile.position)
    )
    return fields.serialize_models(preview_files)


def update_preview_file_annotations(project_id, preview_file_id, annotations):
    """
    Update annotations for given preview file.
    """
    preview_file = files_service.get_preview_file_raw(preview_file_id)
    preview_file.update({"annotations": annotations})
    events.emit(
        "preview-file:annotation-update",
        {"preview_file_id": preview_file_id},
        project_id=project_id,
    )
    return {"id": preview_file_id}


def get_processing_preview_files_for_project():
    """
    """
    preview_files = (
        PreviewFile.query
        .join(Task)
        .filter(PreviewFile.status.in_(("Broken", "Processing")))
        .add_column(Task.task_status_id)
        .add_column(Task.entity_id)
    )
    return fields.serialize_models(preview_files)
