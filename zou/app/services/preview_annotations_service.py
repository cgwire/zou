import copy
import math
import os
import shutil
import tempfile
import zipfile
from PIL import Image

from zou.app import config
from zou.app.stores import file_store
from zou.app.stores.redis_lock import with_preview_file_lock
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.task import Task
from zou.app.services import (
    files_service,
    preview_files_service,
)
from zou.app.utils import (
    annotations as annotations_renderer,
    events,
    fields,
    fs,
)
from zou.app.exceptions import (
    AnnotationLockTimeoutException,
    AnnotationNotFoundException,
    WrongParameterException,
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
):
    """
    Update annotations for given preview file.
    Uses a Redis lock to prevent race conditions when multiple processes update
    annotations on the same preview file concurrently.
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


def _ensure_object_id(drawing_object):
    """
    Give a drawing object an id when it carries none, so later updates and
    deletions can address it. A missing key, an empty string and an
    explicit null all count as none.
    """
    if not drawing_object.get("id"):
        drawing_object["id"] = str(fields.gen_uuid())


def _clean_annotations(annotations):
    """
    Give every drawing object an id, so later updates and deletions can
    address it.
    """
    for annotation in annotations:
        objects = annotation.get("drawing", {}).get("objects", [])
        for current_object in objects:
            _ensure_object_id(current_object)
    return annotations


def _apply_annotation_additions(previous_annotations, new_annotations):
    """
    Add the annotations of times not annotated yet, and merge the new
    drawing objects into the times already annotated.
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
    Replace the drawing objects an update carries, matched by id, at the
    times the update names.
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
    Drop the drawing objects a deletion names, matched by id.
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
    Return the previous drawing objects plus the ones whose id is not
    among them: an addition never overwrites an existing object.
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
    Index annotations by their time, the key a revision is annotated on.
    """
    annotation_map = {}
    for annotation in annotations:
        annotation_map[annotation["time"]] = annotation
    return annotation_map


def _clear_empty_annotations(annotations):
    """
    Drop the times left without a single drawing object.
    """
    return [
        annotation
        for annotation in annotations
        if len(annotation.get("drawing", {}).get("objects", [])) > 0
    ]


def _round_time_to_frame(time_value, fps):
    """
    Snap a playback time onto the frame grid the Kitsu player uses:
    the frame duration is 1 / fps rounded to 4 decimals, and rounding is
    half-up to mirror the JavaScript Math.round used client-side.
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
    Collapse annotation entries that land on the same frame into one and
    snap every entry time onto the frame grid.

    Older Kitsu versions stored unrounded times (sometimes as strings)
    while current ones snap them to the frame grid, so the same logical
    frame can exist several times in a preview file's annotation list.
    The player only displays the first entry matching a frame, which makes
    the other entries' drawings invisible, and grid-timed deletions or
    updates never match the legacy entries.

    Objects are deduplicated by id and the input list is not mutated.
    Returns a (annotations, changed) tuple; entries with unparseable times
    are kept untouched.
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
    Normalize a preview file's annotation times in place (see
    normalize_annotation_times). Returns True when the stored annotations
    were modified.
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
    Extract the requested frame of a movie preview, or the picture itself
    for a picture preview, and overlay the matching annotation on it.

    For movies, `frame_number` is required and identifies the frame. For
    pictures, `frame_number` is ignored and the first annotation entry is
    used.

    Raises AnnotationNotFoundException when no annotation matches. Returns
    the path to the composited PNG (caller must delete it), or None when
    the preview binary is not available.
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
    Build a zip archive containing every annotated frame of a movie
    preview, or every annotated copy of a picture preview.

    Raises AnnotationNotFoundException when the preview has no
    annotations. Returns the path to a temp zip file (caller must delete
    it), or None when the preview binary is not available.
    """
    entries = _build_annotated_frame_entries(preview_file)
    if entries is None:
        return None
    return _bundle_annotated_frames_into_zip(entries)


def extract_all_annotation_frames_pdf_from_preview_file(preview_file):
    """
    Build a multi-page PDF with one page per annotated frame (movie) or
    per annotated copy of the picture (picture preview).

    Raises AnnotationNotFoundException when the preview has no
    annotations. Returns the path to a temp pdf file (caller must delete
    it), or None when the preview binary is not available.
    """
    entries = _build_annotated_frame_entries(preview_file)
    if entries is None:
        return None
    return _bundle_annotated_frames_into_pdf(entries)


def _extract_movie_annotation_frame(preview_file, frame_number, annotations):
    """
    Extract the frame of a movie at given number with its annotations
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
    Copy a picture preview to a temporary png, the format the annotation
    burner works on.
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
        # Only an absent binary answers None (the routes turn it into a
        # 404). A storage outage or a bug must surface as what it is.
        return None
    fd, temp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    with Image.open(picture_path) as img:
        img.convert("RGBA").save(temp_path, "PNG")
    return temp_path


def _find_annotation_at_time(annotations, target_time, tolerance):
    """
    Return the annotation closest to given time within tolerance, None
    when the frame carries none.
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
    Common entry-point for the zip and pdf bundlers: render every
    annotated frame of the preview to a temp PNG and return the list of
    (arcname, path) tuples. Returns None when the binary is unavailable;
    raises AnnotationNotFoundException when there is nothing to render
    and WrongParameterException for unsupported extensions.
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
    Returns a list of (arcname, temp_png_path) tuples ready to be zipped,
    or None if the movie binary is unavailable. Cleans up partial work on
    failure.

    Individual annotations whose frame ffmpeg fails to extract (returns
    a path to a non-existent file, e.g. when the annotation's time falls
    past the movie's EOF) are skipped rather than aborting the whole
    bundle.
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
    Build the annotated frame entries of a picture preview: at most one,
    since a picture carries a single annotation time.
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
    Build the file name stem the extracted annotated frames are named on.
    """
    full_name = preview_files_service.get_preview_file_name(preview_file["id"])
    return os.path.splitext(full_name)[0]


def _claim_extracted_frame(extracted_path):
    """
    Move the frame ffmpeg wrote at a deterministic
    `tmp/<movie>_<frame>.png` slot to a fresh mkstemp path. Required
    because that deterministic slot is shared with other callers (e.g.
    the single-frame extract route which `os.remove`s it in a finally),
    and concurrent calls could yank the file from under the bundler.
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
    Pack the extracted annotated frames into a zip and return its path.
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
    Stitch every PNG into a multi-page PDF via Pillow. PDF doesn't
    support alpha, so each frame is flattened to RGB. 150 DPI keeps page
    sizes reasonable for HD frames without blowing up the file.
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
