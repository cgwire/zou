import copy
import math
import os
import shutil
import tempfile
import zipfile

from PIL import Image

from zou.app import config
from zou.app.exceptions import (
    AnnotationLockTimeoutException,
    AnnotationNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    files_service,
    preview_files_service,
)
from zou.app.stores import file_store
from zou.app.stores.redis_lock import with_preview_file_lock
from zou.app.utils import (
    annotations as annotations_renderer,
    events,
    fields,
    fs,
)

ANNOTATED_PICTURE_EXTENSIONS = ("jpg", "jpeg", "jpe", "png")
_NO_FRAME_EXTRACTED_MSG = (
    "No annotated frame could be extracted from this preview"
)


def update_preview_file_annotations(
    person_id,
    project_id,
    preview_file_id,
    additions=None,
    updates=None,
    deletions=None,
    only_own_objects=False,
):
    """
    Update the annotations of the given preview file and clear its cache.
    Emit preview-file:annotation-update and return the preview file as a
    dict. A Redis lock prevents race conditions when many processes update
    the annotations of the same preview file at the same time. If the lock
    is not available, raise AnnotationLockTimeoutException.

    With ``only_own_objects`` (guests), stamp the added and updated objects
    with ``person_id``. Keep only the updates and deletions of the objects
    that have this stamp from before. Thus, a guest never changes a drawing
    of the team or of a different guest.
    """
    if additions is None:
        additions = []
    if updates is None:
        updates = []
    if deletions is None:
        deletions = []
    with with_preview_file_lock(
        preview_file_id, timeout=30, wait_timeout=35
    ) as acquired:
        if not acquired:
            raise AnnotationLockTimeoutException(
                "Could not acquire annotation lock for preview file"
            )
        preview_file = files_service.get_preview_file_raw(preview_file_id)
        previous_annotations = copy.deepcopy(preview_file.annotations or [])
        if only_own_objects:
            _keep_own_objects(
                previous_annotations, person_id, additions, updates, deletions
            )
        annotations = _clean_annotations(previous_annotations)
        annotations = _apply_annotation_additions(
            previous_annotations, additions
        )
        annotations = _apply_annotation_updates(annotations, updates)
        annotations = _apply_annotation_deletions(annotations, deletions)
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


def _keep_own_objects(
    previous_annotations, person_id, additions, updates, deletions
):
    """
    Stamp the added and updated objects with ``person_id``. Remove from the
    updates and deletions all the objects that do not have this stamp. The
    key of an object is (time, id), as in the updates and deletions. Thus,
    an addition that uses the id of an object at a different time gives no
    access.
    """
    own = {
        (annotation["time"], drawing_object.get("id"))
        for annotation in previous_annotations
        for drawing_object in annotation.get("drawing", {}).get(
            "objects", []
        )
        if drawing_object.get("person_id") == person_id
    }
    for annotation in additions + updates:
        for drawing_object in annotation.get("drawing", {}).get(
            "objects", []
        ):
            drawing_object["person_id"] = person_id
    for update in updates:
        drawing = update.setdefault("drawing", {})
        drawing["objects"] = [
            drawing_object
            for drawing_object in drawing.get("objects", [])
            if (update["time"], drawing_object.get("id")) in own
        ]
    for deletion in deletions:
        deletion["objects"] = [
            object_id
            for object_id in deletion.get("objects", [])
            if (deletion["time"], object_id) in own
        ]


def _ensure_object_id(drawing_object):
    """
    If a drawing object has no id, give it one. Thus, later updates and
    deletions can find it. A missing key, an empty string and an explicit
    null all count as no id.
    """
    if not drawing_object.get("id"):
        drawing_object["id"] = str(fields.gen_uuid())


def _clean_annotations(annotations):
    """
    Give an id to each drawing object. Thus, later updates and deletions can
    find it.
    """
    for annotation in annotations:
        objects = annotation.get("drawing", {}).get("objects", [])
        for current_object in objects:
            _ensure_object_id(current_object)
    return annotations


def _apply_annotation_additions(previous_annotations, new_annotations):
    """
    Add the annotations of the times that have no annotation yet. Merge the
    new drawing objects into the times that already have annotations.
    """
    annotations = list(previous_annotations)
    annotation_map = _get_annotation_time_map(annotations)

    for new_annotation in new_annotations:
        previous_annotation = annotation_map.get(new_annotation["time"], None)
        if previous_annotation is None:
            new_objects = new_annotation.get("drawing", {}).get("objects", [])
            for new_object in new_objects:
                _ensure_object_id(new_object)
            annotations.append(new_annotation)
        else:
            previous_objects = previous_annotation.get("drawing", {}).get(
                "objects", []
            )
            new_objects = new_annotation.get("drawing", {}).get("objects", [])
            for new_object in new_objects:
                _ensure_object_id(new_object)
            previous_annotation["drawing"]["objects"] = _get_new_annotations(
                previous_objects, new_objects
            )
    return annotations


def _apply_annotation_updates(annotations, updates):
    """
    Replace the drawing objects of an update, matched by id, at the times
    that the update gives.
    """
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
                if "id" in previous_object:
                    previous_object_map[previous_object["id"]] = (
                        previous_object
                    )

            updated_objects = update.get("drawing", {}).get("objects", [])
            for updated_object in updated_objects:
                if "id" in updated_object:
                    update_map[updated_object["id"]] = update

            result = [
                previous_object
                for previous_object in previous_objects
                if previous_object.get("id", None) not in update_map
            ]
            for updated_object in updated_objects:
                if (
                    "id" in updated_object
                    and updated_object["id"] in previous_object_map
                ):
                    result.append(updated_object)
            annotation["drawing"]["objects"] = result
    return annotations


def _apply_annotation_deletions(annotations, deletions):
    """
    Remove the drawing objects that a deletion gives, matched by id.
    """
    annotation_map = _get_annotation_time_map(annotations)

    for deletion in deletions:
        if deletion["time"] in annotation_map:
            annotation = annotation_map[deletion["time"]]
            deleted_object_ids = deletion.get("objects", [])
            if "drawing" not in annotation or not isinstance(
                annotation["drawing"], dict
            ):
                annotation["drawing"] = {}
            previous_objects = annotation["drawing"].get("objects", [])
            annotation["drawing"]["objects"] = [
                previous_object
                for previous_object in previous_objects
                if previous_object.get("id", "") not in deleted_object_ids
            ]

    return _clear_empty_annotations(annotations)


def _get_new_annotations(previous_objects, new_objects):
    """
    Return the previous drawing objects and the new objects whose id is not
    in them. An addition never overwrites an existing object.
    """
    result = list(previous_objects)
    previous_map = {}
    for previous_object in result:
        _ensure_object_id(previous_object)
        previous_map[previous_object["id"]] = True

    for new_object in new_objects:
        object_id = new_object.get("id", "")
        if object_id not in previous_map:
            result.append(new_object)
    return result


def _get_annotation_time_map(annotations):
    """
    Index the annotations by their time. A revision uses the time as the
    key of its annotations.
    """
    annotation_map = {}
    for annotation in annotations:
        annotation_map[annotation["time"]] = annotation
    return annotation_map


def _clear_empty_annotations(annotations):
    """
    Remove the times that have no drawing object.
    """
    return [
        annotation
        for annotation in annotations
        if len(annotation.get("drawing", {}).get("objects", [])) > 0
    ]


def _round_time_to_frame(time_value, fps):
    """
    Snap a playback time onto the frame grid of the Kitsu player. The frame
    duration is 1 / fps, rounded to 4 decimals. The rounding is half-up, as
    the JavaScript Math.round that the client uses.
    """
    precision_factor = 10000
    frame_duration = (
        math.floor(1 / fps * precision_factor + 0.5) / precision_factor
    )
    frame_number = math.floor(time_value / frame_duration + 0.5)
    return (
        math.floor(frame_number * frame_duration * precision_factor + 0.5)
        / precision_factor
    )


def normalize_annotation_times(annotations, fps):
    """
    Merge the annotation entries of the same frame into one entry. Snap the
    time of each entry onto the frame grid.

    Old Kitsu versions stored times that are not rounded, sometimes as
    strings. The current versions snap them to the frame grid. Thus, the
    same logical frame can occur many times in the annotation list of a
    preview file. The player shows only the first entry of a frame. Thus,
    the drawings of the other entries are not visible. Also, the deletions
    and updates on the grid times never match the old entries.

    Remove the duplicate objects by id. Do not change the input list.
    Return an (annotations, changed) tuple. Keep the entries whose times
    cannot be parsed as they are.
    """
    result = []
    by_frame_time = {}
    changed = False
    for annotation in annotations or []:
        try:
            time_value = max(float(annotation.get("time") or 0), 0.0)
        except (TypeError, ValueError):
            result.append(copy.deepcopy(annotation))
            continue
        frame_time = _round_time_to_frame(time_value, fps)
        existing = by_frame_time.get(frame_time)
        objects = (annotation.get("drawing") or {}).get("objects", [])
        if existing is None:
            entry = copy.deepcopy(annotation)
            if entry.get("time") != frame_time:
                changed = True
            entry["time"] = frame_time
            entry["drawing"] = {
                **(entry.get("drawing") or {}),
                "objects": (entry.get("drawing") or {}).get("objects", []),
            }
            by_frame_time[frame_time] = entry
            result.append(entry)
        else:
            changed = True
            seen_ids = {
                existing_object.get("id")
                for existing_object in existing["drawing"]["objects"]
            }
            existing["drawing"]["objects"].extend(
                copy.deepcopy(new_object)
                for new_object in objects
                if new_object.get("id") not in seen_ids
            )
    return result, changed


def normalize_preview_file_annotation_times(preview_file):
    """
    Normalize the annotation times of a preview file in place (see
    normalize_annotation_times). If the stored annotations changed, return
    True.
    """
    if not preview_file.annotations:
        return False
    task = Task.get(preview_file.task_id)
    project = Project.get(task.project_id).serialize()
    entity = Entity.get(task.entity_id)
    fps = float(
        preview_files_service.get_preview_file_fps(
            project, entity.serialize() if entity is not None else None
        )
    )
    annotations, changed = normalize_annotation_times(
        preview_file.annotations, fps
    )
    if changed:
        preview_file.update({"annotations": annotations})
        files_service.clear_preview_file_cache(str(preview_file.id))
    return changed


def extract_annotation_frame_from_preview_file(
    preview_file, frame_number=None
):
    """
    Extract the requested frame of a movie preview, or the picture of a
    picture preview. Put the related annotation on it.

    For movies, `frame_number` is necessary and identifies the frame. For
    pictures, ignore `frame_number` and use the first annotation entry.

    If no annotation matches, raise AnnotationNotFoundException. If a movie
    has no frame number, or if the extension is not supported, raise
    WrongParameterException. Return the path to the composited PNG. The
    caller must delete it. If the preview binary is not available, return
    None.
    """
    extension = (preview_file.get("extension") or "").lower()
    annotations = preview_file.get("annotations") or []
    if extension == "mp4":
        if frame_number is None:
            raise WrongParameterException(
                "frame_number is required for movie previews"
            )
        return _extract_movie_annotation_frame(
            preview_file, frame_number, annotations
        )
    if extension in ANNOTATED_PICTURE_EXTENSIONS:
        return _extract_picture_annotation_frame(preview_file, annotations)
    raise WrongParameterException(
        f"Cannot extract annotated frame from preview with extension "
        f"{extension!r}"
    )


def extract_all_annotation_frames_from_preview_file(preview_file):
    """
    Build a zip archive with all the annotated frames of a movie preview, or
    all the annotated copies of a picture preview.

    If the preview has no annotations, raise AnnotationNotFoundException.
    Return the path to a temporary zip file. The caller must delete it. If
    the preview binary is not available, return None.
    """
    entries = _build_annotated_frame_entries(preview_file)
    if entries is None:
        return None
    return _bundle_annotated_frames_into_zip(entries)


def extract_all_annotation_frames_pdf_from_preview_file(preview_file):
    """
    Build a multi-page PDF with one page for each annotated frame (movie)
    or for each annotated copy of the picture (picture preview).

    If the preview has no annotations, raise AnnotationNotFoundException.
    Return the path to a temporary pdf file. The caller must delete it. If
    the preview binary is not available, return None.
    """
    entries = _build_annotated_frame_entries(preview_file)
    if entries is None:
        return None
    return _bundle_annotated_frames_into_pdf(entries)


def _extract_movie_annotation_frame(preview_file, frame_number, annotations):
    """
    Extract the frame of a movie at the given number, with its annotations
    burnt in.
    """
    project = preview_files_service.get_project_from_preview_file(
        preview_file["id"]
    )
    entity = preview_files_service.get_entity_from_preview_file(
        preview_file["id"]
    )
    fps = float(preview_files_service.get_preview_file_fps(project, entity))
    target_time = (frame_number - 1) / fps
    tolerance = 1 / (2 * fps)
    annotation = _find_annotation_at_time(annotations, target_time, tolerance)
    if annotation is None:
        raise AnnotationNotFoundException(
            f"No annotation found for frame {frame_number}"
        )
    frame_path = preview_files_service.extract_frame_from_preview_file(
        preview_file, frame_number
    )
    if frame_path is None:
        return None
    return annotations_renderer.render_annotation_on_image(
        frame_path, annotation
    )


def _extract_picture_annotation_frame(preview_file, annotations):
    """
    Render a picture preview with its annotations burnt in.
    """
    if not annotations:
        raise AnnotationNotFoundException(
            "No annotation found on picture preview"
        )
    picture_copy = _copy_picture_preview_to_temp_png(preview_file)
    if picture_copy is None:
        return None
    return annotations_renderer.render_annotation_on_image(
        picture_copy, annotations[0]
    )


def _copy_picture_preview_to_temp_png(preview_file):
    """
    Copy a picture preview to a temporary png. The annotation burner uses
    this format.
    """
    if (preview_file.get("data") or {}).get("imported_only"):
        return None
    try:
        picture_path = fs.get_file_path_and_file(
            config,
            file_store.get_local_picture_path,
            file_store.open_picture,
            "previews",
            preview_file["id"],
            preview_file["extension"],
        )
    except fs.FileNotFound:
        # Return None only for a missing binary (the routes change it into a
        # 404). Do not hide a storage outage or a bug.
        return None
    fd, temp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with Image.open(picture_path) as img:
        img.convert("RGBA").save(temp_path, "PNG")
    return temp_path


def _find_annotation_at_time(annotations, target_time, tolerance):
    """
    Return the annotation nearest to the given time, within the tolerance.
    If the frame has no annotation, return None.
    """
    for annotation in annotations:
        raw_time = annotation.get("time")
        if raw_time is None:
            continue
        try:
            annotation_time = float(raw_time)
        except (TypeError, ValueError):
            continue
        if abs(annotation_time - target_time) <= tolerance:
            return annotation
    return None


def _build_annotated_frame_entries(preview_file):
    """
    Common entry point for the zip and pdf bundlers. Render each annotated
    frame of the preview to a temporary PNG. Return the list of
    (arcname, path) tuples.
    - If the binary is not available, return None.
    - If there is nothing to render, raise AnnotationNotFoundException.
    - If the extension is not supported, raise WrongParameterException.
    """
    annotations = preview_file.get("annotations") or []
    if not annotations:
        raise AnnotationNotFoundException("Preview file has no annotations")
    extension = (preview_file.get("extension") or "").lower()
    base_name = _annotated_frame_base_name(preview_file)
    if extension == "mp4":
        return _build_movie_annotation_entries(
            preview_file, annotations, base_name
        )
    if extension in ANNOTATED_PICTURE_EXTENSIONS:
        return _build_picture_annotation_entries(
            preview_file, annotations, base_name
        )
    raise WrongParameterException(
        f"Cannot extract annotated frames from preview with extension "
        f"{extension!r}"
    )


def _build_movie_annotation_entries(preview_file, annotations, base_name):
    """
    Return a list of (arcname, temp_png_path) tuples, ready for the bundle.
    If the movie binary is not available, return None. If a failure
    occurs, remove the partial files.

    Sometimes ffmpeg cannot extract the frame of an annotation. Then it
    returns a path to a file that does not exist, for example when the
    time of the annotation is after the EOF of the movie. Skip these
    annotations and continue the bundle.
    """
    project = preview_files_service.get_project_from_preview_file(
        preview_file["id"]
    )
    entity = preview_files_service.get_entity_from_preview_file(
        preview_file["id"]
    )
    fps = float(preview_files_service.get_preview_file_fps(project, entity))
    entries = []
    try:
        for annotation in annotations:
            raw_time = annotation.get("time")
            try:
                annotation_time = float(raw_time)
            except (TypeError, ValueError):
                continue
            frame_number = max(1, round(annotation_time * fps) + 1)
            frame_path = preview_files_service.extract_frame_from_preview_file(
                preview_file, frame_number
            )
            if frame_path is None:
                _cleanup_entries(entries)
                return None
            if not os.path.exists(frame_path):
                continue
            owned_path = _claim_extracted_frame(frame_path)
            rendered = annotations_renderer.render_annotation_on_image(
                owned_path, annotation
            )
            entries.append((f"{base_name}_frame_{frame_number}.png", rendered))
    except Exception:
        _cleanup_entries(entries)
        raise
    return entries


def _build_picture_annotation_entries(preview_file, annotations, base_name):
    """
    Build the annotated frame entries of a picture preview. Make one copy
    of the picture for each annotation, with that annotation burnt in.
    """
    entries = []
    try:
        for index, annotation in enumerate(annotations, start=1):
            picture_copy = _copy_picture_preview_to_temp_png(preview_file)
            if picture_copy is None:
                _cleanup_entries(entries)
                return None
            rendered = annotations_renderer.render_annotation_on_image(
                picture_copy, annotation
            )
            entries.append((f"{base_name}_frame_{index}.png", rendered))
    except Exception:
        _cleanup_entries(entries)
        raise
    return entries


def _annotated_frame_base_name(preview_file):
    """
    Build the file name stem of the extracted annotated frames.
    """
    full_name = preview_files_service.get_preview_file_name(preview_file["id"])
    return os.path.splitext(full_name)[0]


def _claim_extracted_frame(extracted_path):
    """
    Move the frame that ffmpeg wrote at the fixed
    `tmp/<movie>_<frame>.png` path to a new mkstemp path. This is
    necessary because other callers use the same fixed path. For example,
    the single-frame extract route removes it with `os.remove` in a
    finally block. Thus, a parallel call can remove the file before the
    bundler uses it.
    """
    fd, owned_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    shutil.move(extracted_path, owned_path)
    return owned_path


def _cleanup_entries(entries):
    """
    Remove the temporary files of the extracted frames.
    """
    for _, path in entries:
        if path and os.path.exists(path):
            os.remove(path)


def _bundle_annotated_frames_into_zip(entries):
    """
    Put the extracted annotated frames into a zip and return its path.
    """
    if not entries:
        raise AnnotationNotFoundException(_NO_FRAME_EXTRACTED_MSG)
    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for arcname, src_path in entries:
                zf.write(src_path, arcname=arcname)
    except Exception:
        preview_files_service.remove_temp_files(zip_path)
        raise
    finally:
        _cleanup_entries(entries)
    return zip_path


def _bundle_annotated_frames_into_pdf(entries):
    """
    Join all the PNG files into a multi-page PDF with Pillow. PDF does not
    support alpha. Thus, flatten each frame to RGB. At 150 DPI, the pages
    of HD frames have a good size and the file stays small.
    """
    if not entries:
        raise AnnotationNotFoundException(_NO_FRAME_EXTRACTED_MSG)
    fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    images = []
    try:
        for _, src_path in entries:
            images.append(Image.open(src_path).convert("RGB"))
        head, tail = images[0], images[1:]
        head.save(
            pdf_path,
            "PDF",
            save_all=True,
            append_images=tail,
            resolution=150.0,
        )
    except Exception:
        preview_files_service.remove_temp_files(pdf_path)
        raise
    finally:
        for img in images:
            img.close()
        _cleanup_entries(entries)
    return pdf_path
