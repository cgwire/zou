from flasgger import swag_from
import os
import unicodedata
from urllib.parse import quote
import orjson as json

from flask import request, current_app, jsonify, Response
from flask import send_file as flask_send_file
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from flask_fs.errors import FileNotFound
from werkzeug.exceptions import NotFound
from werkzeug.wsgi import FileWrapper as WerkzeugFileWrapper

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.utils import validation as validation_utils
from zou.app.blueprints.previews.schemas import (
    AnnotationsUpdateSchema,
    ExtractAnnotatedFrameSchema,
    PreviewFileUploadSchema,
    PreviewFilePositionSchema,
)
from zou.app.stores import file_store
from zou.app.services import (
    comments_service,
    chats_service,
    deletion_service,
    entities_service,
    files_service,
    persons_service,
    projects_service,
    preview_file_states_service,
    preview_files_service,
    tasks_service,
    permissions_service,
    organisation_service,
    task_types_service,
    preview_annotations_service,
    preview_maintenance_service,
    attachment_files_service,
)
from zou.utils import movie
from zou.app.utils import (
    fields,
    fs,
    events,
    permissions,
    thumbnail as thumbnail_utils,
    date_helpers,
)
from zou.app.exceptions import (
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
    PreviewFileReuploadNotAllowedException,
    PreviewProcessingFailedException,
    WrongParameterException,
)

ALLOWED_PICTURE_EXTENSION = {"jpe", "jpeg", "jpg", "png"}
ALLOWED_MOVIE_EXTENSION = {
    "avi",
    "m4v",
    "mkv",
    "mov",
    "mp4",
    "webm",
    "wmv",
}
ALLOWED_FILE_EXTENSION = {
    "ae",
    "ai",
    "blend",
    "clip",
    "comp",
    "diff",
    "exr",
    "fbx",
    "fla",
    "flv",
    "gif",
    "glb",
    "gltf",
    "hip",
    "kra",
    "ma",
    "mb",
    "md",
    "mp3",
    "obj",
    "pdf",
    "psd",
    "psb",
    "rar",
    "rev",
    "riv",
    "sai",
    "sai2",
    "sbbkp",
    "svg",
    "swf",
    "tvpp",
    "wav",
    "zip",
}
ALLOWED_PREVIEW_BACKGROUND_EXTENSION = {"hdr"}


PROCESSING_RETRY_AFTER = 5


def send_standard_file(
    preview_file_id,
    extension,
    mimetype="application/octet-stream",
    as_attachment=False,
    last_modified=None,
):
    return send_storage_file(
        file_store.get_local_file_path,
        file_store.open_file,
        "previews",
        preview_file_id,
        extension,
        mimetype=mimetype,
        as_attachment=as_attachment,
        last_modified=last_modified,
    )


class SeekableFileWrapper(WerkzeugFileWrapper):
    """
    Werkzeug's file wrapper (it seeks, gunicorn's does not) with the
    attribute gunicorn's sendfile path reads on a response that is an
    instance of the wrapper found in wsgi.file_wrapper.
    """

    @property
    def filelike(self):
        return self.file


def get_single_byte_range():
    """
    The request's Range header when it asks for one byte range, the way
    a movie player does. None otherwise: a multipart range gets the whole
    file, like no range at all.
    """
    byte_range = request.range
    if (
        byte_range is not None
        and byte_range.units == "bytes"
        and len(byte_range.ranges) == 1
    ):
        return byte_range.to_header()
    return None


def stream_movie_from_storage(
    prefix,
    preview_file_id,
    range_header,
    mimetype,
    as_attachment,
    download_name,
    max_age,
):
    """
    Serve a movie that is not in the local cache yet straight from the
    object storage, so the first play does not wait for the whole file to
    land on the disk.
    """
    content_length, content_range, generator = file_store.read_movie_range(
        prefix, preview_file_id, range_header
    )
    response = Response(
        generator,
        status=206 if content_range else 200,
        mimetype=mimetype,
        direct_passthrough=True,
    )
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = content_length
    if content_range:
        response.headers["Content-Range"] = content_range
    if as_attachment:
        # Same folding as werkzeug's send_file on the warm path: a raw
        # non-ASCII name is an invalid header value for gunicorn.
        try:
            download_name.encode("ascii")
            names = {"filename": download_name}
        except UnicodeEncodeError:
            simple = unicodedata.normalize("NFKD", download_name)
            names = {
                "filename": simple.encode("ascii", "ignore").decode("ascii"),
                "filename*": "UTF-8''"
                + quote(download_name, safe="!#$&+-.^_`|~"),
            }
        response.headers.set("Content-Disposition", "attachment", **names)
    response.cache_control.private = True
    response.cache_control.max_age = max_age
    return response


def wants_json_over_picture():
    """
    Whether the client would rather read JSON than an image. A browser
    asks for image/* explicitly and keeps the 404 it knows how to
    handle; a client that says Accept: application/json is told the file
    is on its way.
    """
    accept = request.accept_mimetypes
    return accept["application/json"] > accept["image/png"]


def preview_processing_response(preview_file_id):
    """
    The answer for a preview file whose files are still being built: not
    an error, and never cached.
    """
    response = jsonify(
        {"status": "processing", "preview_file_id": preview_file_id}
    )
    response.status_code = 202
    response.headers["Retry-After"] = str(PROCESSING_RETRY_AFTER)
    response.cache_control.no_store = True
    return response


def _processing_answer(preview_file_id):
    """
    The answer to give for a preview file being processed, or None when
    it is not. A JSON client is told to come back; everyone else gets the
    404 they already handle. No storage state is recorded either way: an
    absence that is expected is not an absence.

    The 404 case is built and returned here, rather than raised as
    FileNotFound, so it carries Cache-Control: no-store. Raising it would
    let it surface as a bare werkzeug 404 (via PreviewFileNotFoundException
    in the caller), which a browser is free to cache heuristically and
    keep showing once the preview turns ready.
    """
    preview_file = files_service.get_preview_file_for_access(preview_file_id)
    # .get: an entry memoized by a version predating "status" survives a
    # deploy for the cache TTL.
    if preview_file.get("status") == "processing":
        # The memoized status can outlive the job that made the preview
        # ready: a cache local to this process, or a read racing the
        # clear that followed the job's update.
        files_service.clear_preview_file_cache(preview_file_id)
        preview_file = files_service.get_preview_file_for_access(
            preview_file_id
        )
    if preview_file.get("status") != "processing":
        return None
    if wants_json_over_picture():
        return preview_processing_response(preview_file_id)
    response = jsonify(error=True, message="Preview file was not found.")
    response.status_code = 404
    response.cache_control.no_store = True
    return response


def send_movie_file(
    preview_file_id,
    as_attachment=False,
    lowdef=False,
    last_modified=None,
    preview_file=None,
):
    """
    Send the requested movie version, falling back on the other stored ones.
    A setup skipping part of the normalization (SKIP_NORMALIZATION_FULL,
    SKIP_NORMALIZATION_HIGHDEF) stores a single version, and the uploaded
    source is the last resort. Note that the source is served as video/mp4
    whatever its real container, and carries no faststart flag.

    The versions actually stored come first: a missing object costs a
    round trip on the object storage, and a movie player asks for the same
    file once per range. They are read from the access lookup the route
    already did (`preview_file`). A preview file that predates the record
    is served in the default order, and the record is probed and written
    back after the response starts: the probe costs one round trip per
    version, more than the movie read itself. Versions known missing are
    skipped until the recheck delay has elapsed.
    """
    if preview_file is None:
        preview_file = files_service.get_preview_file_for_access(
            preview_file_id
        )
    processing = _processing_answer(preview_file_id)
    if processing is not None:
        return processing
    # .get: a dict memoized by the previous release has no such key.
    recorded_prefixes = preview_file.get("movie_prefixes")
    prefixes = files_service.get_movie_prefixes(
        recorded_prefixes or [], lowdef
    )
    states = preview_file_states_service.get_file_states(preview_file_id)
    candidates = [
        prefix
        for prefix in prefixes
        if not preview_file_states_service.is_known_missing(
            states, "movies", prefix
        )
    ]
    if not candidates:
        raise FileNotFound(f"movies-{preview_file_id}")
    for prefix in candidates:
        try:
            response = send_storage_file(
                file_store.get_local_movie_path,
                file_store.open_movie,
                prefix,
                preview_file_id,
                "mp4",
                mimetype="video/mp4",
                as_attachment=as_attachment,
                last_modified=last_modified,
                stream_cold=True,
            )
        except FileNotFound as exception:
            if isinstance(exception, fs.ConfirmedFileNotFound):
                _record_confirmed_missing(
                    states, "movies", prefix, preview_file_id
                )
            if prefix == candidates[-1]:
                raise
            continue
        preview_file_states_service.record_file_state(
            preview_file_id, "movies", prefix, preview_file_states_service.OK
        )
        if recorded_prefixes is None or prefix != prefixes[0]:
            # No record yet, or one lagging behind the storage (a version
            # removed, a row imported from another instance).
            files_service.record_movie_prefixes_later(
                preview_file_id, prefix, recorded_prefixes
            )
        return response


def send_source_movie_file(preview_file_id, last_modified=None):
    """
    Send the uploaded source movie, and only that one: the sync between two
    instances has to tell it apart from the encoded versions.
    """
    return send_storage_file(
        file_store.get_local_movie_path,
        file_store.open_movie,
        "source",
        preview_file_id,
        "mp4",
        mimetype="video/mp4",
        last_modified=last_modified,
    )


def send_picture_file(
    prefix,
    preview_file_id,
    as_attachment=False,
    extension="png",
    download_name="",
    last_modified=None,
):
    if extension == "png":
        mimetype = "image/png"
    elif extension == "hdr":
        mimetype = "image/vnd.radiance"
    else:
        mimetype = "application/octet-stream"
    return send_storage_file(
        file_store.get_local_picture_path,
        file_store.open_picture,
        prefix,
        preview_file_id,
        extension,
        mimetype=mimetype,
        as_attachment=as_attachment,
        download_name=download_name,
        last_modified=last_modified,
    )


def send_preview_picture_file(prefix, preview_file_id, **kwargs):
    """
    send_picture_file for a picture of a preview file, keeping its storage
    state: a file known missing is answered 404 without asking the
    storage, a confirmed 404 is recorded, a successful read too.
    """
    return _send_preview_variant(
        "pictures",
        prefix,
        preview_file_id,
        lambda: send_picture_file(prefix, preview_file_id, **kwargs),
    )


def send_preview_standard_file(preview_file_id, extension, **kwargs):
    """
    send_standard_file for a non picture, non movie preview file, keeping
    its storage state like send_preview_picture_file.
    """
    return _send_preview_variant(
        "files",
        "previews",
        preview_file_id,
        lambda: send_standard_file(preview_file_id, extension, **kwargs),
    )


def _send_preview_variant(bucket, prefix, preview_file_id, send):
    processing = _processing_answer(preview_file_id)
    if processing is not None:
        return processing
    states = preview_file_states_service.get_file_states(preview_file_id)
    if preview_file_states_service.is_known_missing(states, bucket, prefix):
        raise FileNotFound(f"{prefix}-{preview_file_id}")
    try:
        response = send()
    except fs.ConfirmedFileNotFound:
        _record_confirmed_missing(states, bucket, prefix, preview_file_id)
        raise
    preview_file_states_service.record_file_state(
        preview_file_id, bucket, prefix, preview_file_states_service.OK
    )
    return response


def _record_confirmed_missing(states, bucket, prefix, preview_file_id):
    """
    A file that failed to be generated stays failed; the date is always
    refreshed, so the short-circuit applies for another delay.
    """
    current = preview_file_states_service.get_state(states, bucket, prefix)
    state = (
        preview_file_states_service.FAILED
        if current == preview_file_states_service.FAILED
        else preview_file_states_service.MISSING
    )
    preview_file_states_service.record_file_state(
        preview_file_id, bucket, prefix, state, refresh=True
    )


def send_storage_file(
    get_local_path,
    open_file,
    prefix,
    preview_file_id,
    extension,
    mimetype="application/octet-stream",
    as_attachment=False,
    max_age=config.CLIENT_CACHE_MAX_AGE,
    download_name="",
    last_modified=None,
    stream_cold=False,
):
    """
    Send file from storage. If it's not a local storage, cache the file in
    a temporary folder before sending it. It accepts conditional headers.

    With ``stream_cold``, a movie missing from that cache is streamed from
    the storage right away while a background download fills the cache.
    Only a ranged request (a player) is served that way: a whole-file
    request would cost two full storage reads and lose the validators.
    """
    file_size = None
    try:
        # The recorded file_size is the one of the normalized movie, the
        # "previews" version (a "movies" prefix never existed): the low
        # def and source versions have their own sizes. For a movie it
        # only guards the cache copy of an object store: the local store
        # has no copy to go stale, and the size lags behind the file
        # while a movie is renormalized, which would flag the high def
        # version as missing.
        is_cached_movie = (
            prefix == "previews"
            and extension == "mp4"
            and config.FS_BACKEND != "local"
        )
        if is_cached_movie or prefix in ["original", "preview-backgrounds"]:
            if prefix == "preview-backgrounds":
                preview_file = files_service.get_preview_background_file(
                    preview_file_id
                )
            else:
                preview_file = files_service.get_preview_file(preview_file_id)
            if (
                preview_file.get("file_size") is not None
                and preview_file["file_size"] > 0
                and preview_file["extension"] == extension
            ):
                file_size = preview_file["file_size"]
    except NotFound:
        pass
    if as_attachment:
        download_name = preview_files_service.get_preview_file_name(
            preview_file_id
        )

    # Werkzeug never starts the body generator of a HEAD response: a
    # storage stream opened for it would only be closed by refcount.
    range_header = (
        get_single_byte_range()
        if stream_cold and request.method != "HEAD"
        else None
    )
    if range_header and file_store.can_stream_movie_ranges():
        cache_path = fs.get_cache_file_path(
            config, prefix, preview_file_id, extension
        )
        if fs.is_invalid_file(cache_path, file_size):
            # No ETag or Last-Modified on purpose: a browser that got one
            # here would send it back as If-Range once the cache is warm,
            # where send_file computes a different validator and would
            # answer the whole file. The bytes are the same either way.
            response = stream_movie_from_storage(
                prefix,
                preview_file_id,
                range_header,
                mimetype,
                as_attachment,
                download_name,
                max_age,
            )
            # Only once the range read proved the storage holds this
            # prefix: the fallback tries prefixes it may not, and a fill
            # started for a missing one is a wasted download.
            fs.fill_cache_in_background(
                cache_path, open_file, prefix, preview_file_id
            )
            return response

    file_path = fs.get_file_path_and_file(
        config,
        get_local_path,
        open_file,
        prefix,
        preview_file_id,
        extension,
        file_size=file_size,
    )

    # send_file wraps the file in whatever the WSGI server put in
    # wsgi.file_wrapper, and Werkzeug's range wrapper only seeks when that
    # wrapper has a seekable() method. gunicorn's FileWrapper has none, so
    # every Range request read and discarded the file from byte 0 up to the
    # range: linear in the offset, seconds per request at the end of a long
    # movie, blocking the worker. Swap in a seekable wrapper for this
    # response.
    request.environ["wsgi.file_wrapper"] = SeekableFileWrapper
    try:
        response = flask_send_file(
            file_path,
            conditional=True,
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=download_name,
            max_age=max_age,
            last_modified=last_modified,
        )
    except IOError as e:
        current_app.logger.error(e)
        raise FileNotFound
    # Preview bytes are gated by JWT / share-link token: never let a
    # shared proxy store them. Flip Werkzeug's default `public,
    # max-age=N` to `private, max-age=N` so the browser keeps caching
    # but intermediaries don't.
    response.cache_control.public = False
    response.cache_control.private = True
    return response


class BaseNewPreviewFilePicture:
    """
    Base class to add previews.
    """

    def save_picture_preview(self, instance_id, uploaded_file):
        """
        Get uploaded picture, read the metadata the response carries and
        hand the variants over to the job queue.
        """
        tmp_folder = config.TMP_DIR
        original_tmp_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        file_size = fs.get_file_size(original_tmp_path)
        width, height = thumbnail_utils.get_dimensions(original_tmp_path)
        queued = preview_files_service.dispatch_picture_processing(
            instance_id, original_tmp_path, no_job=self.get_no_job()
        )
        return {
            "preview_file_id": instance_id,
            "file_size": file_size,
            "extension": "png",
            "width": width,
            "height": height,
            "queued": queued,
        }

    @staticmethod
    def _get_upload_stream_size(uploaded_file):
        """
        Return the byte size of the uploaded file stream, or None when the
        stream is not seekable.
        """
        try:
            stream = uploaded_file.stream
            position = stream.tell()
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(position)
            return size
        except (AttributeError, OSError, ValueError):
            return None

    def save_movie_preview(
        self, preview_file_id, uploaded_file, normalize=True
    ):
        """
        Get uploaded movie, normalize it then build thumbnails then save
        everything in the file storage.
        """
        no_job = self.get_no_job()
        tmp_folder = config.TMP_DIR
        uploaded_movie_path = movie.save_file(
            tmp_folder, preview_file_id, uploaded_file
        )
        if (
            not os.path.exists(uploaded_movie_path)
            or os.path.getsize(uploaded_movie_path) == 0
        ):
            raise WrongParameterException(
                "Uploaded movie could not be written to temporary storage "
                "or is empty; aborting before dispatching normalization."
            )
        expected_size = self._get_upload_stream_size(uploaded_file)
        written_size = os.path.getsize(uploaded_movie_path)
        if expected_size is not None and written_size != expected_size:
            fs.rm_file(uploaded_movie_path)
            raise PreviewProcessingFailedException(
                f"Uploaded movie was only partially written to temporary "
                f"storage ({written_size}/{expected_size} bytes); the "
                f"temporary disk may be full."
            )
        # The remote worker reads the movie from the object storage, and
        # without normalization that source is the only movie stored: it has
        # to be uploaded whatever PREVIEW_SAVE_SOURCE_FILE says.
        save_source_file = (
            config.PREVIEW_SAVE_SOURCE_FILE
            or preview_files_service.is_remote_normalization_enabled()
        )
        preview_files_service.dispatch_movie_processing(
            preview_file_id,
            uploaded_movie_path,
            normalize=normalize,
            add_source_to_file_store=save_source_file,
            no_job=no_job,
        )
        return preview_file_id

    def save_file_preview(self, instance_id, uploaded_file, extension):
        """
        Get uploaded file then save it in the file storage.
        """
        tmp_folder = config.TMP_DIR
        file_name = f"{instance_id}.{extension}"
        file_path = os.path.join(tmp_folder, file_name)
        uploaded_file.save(file_path)
        try:
            file_store.add_file("previews", instance_id, file_path)
            preview_file_states_service.record_file_state(
                instance_id,
                "files",
                "previews",
                preview_file_states_service.OK,
            )
            file_size = fs.get_file_size(file_path)
            preview_files_service.update_preview_file(
                instance_id, {"file_size": file_size}, silent=True
            )
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
        return file_path

    def emit_app_preview_event(self, preview_file_id):
        """
        Emit an event, each time a preview is added.
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        comment = tasks_service.get_comment_by_preview_file_id(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        comment_id = None
        if comment is not None:
            comment_id = comment["id"]
            events.emit(
                "comment:update",
                {"comment_id": comment_id, "task_id": comment["object_id"]},
                project_id=task["project_id"],
            )
            events.emit(
                "preview-file:add-file",
                {
                    "comment_id": comment_id,
                    "task_id": preview_file["task_id"],
                    "preview_file_id": preview_file["id"],
                    "revision": preview_file["revision"],
                    "extension": preview_file["extension"],
                    "status": preview_file["status"],
                },
                project_id=task["project_id"],
            )

    def process_uploaded_file(
        self, instance_id, uploaded_file, abort_on_failed=False
    ):
        file_name_parts = uploaded_file.filename.split(".")
        extension = file_name_parts.pop().lower()
        original_file_name = ".".join(file_name_parts)
        preview_file = None
        if extension in ALLOWED_PICTURE_EXTENSION:
            metadata = self.save_picture_preview(instance_id, uploaded_file)
            data = {
                "extension": "png",
                "original_name": original_file_name,
                "width": metadata["width"],
                "height": metadata["height"],
                "file_size": metadata["file_size"],
            }
            if not metadata["queued"]:
                data["status"] = "ready"
            preview_file = preview_files_service.update_preview_file(
                instance_id, data
            )
        elif extension in ALLOWED_MOVIE_EXTENSION:
            normalize = self.get_bool_parameter("normalize", "true")
            try:
                self.save_movie_preview(instance_id, uploaded_file, normalize)
            except WrongParameterException:
                # Invalid upload (e.g. empty or corrupted transfer): the file
                # itself is the problem, so keep the original 400 message.
                deletion_service.remove_preview_file_by_id(
                    instance_id, force=True
                )
                if abort_on_failed:
                    raise
                return None
            except Exception as e:
                # Genuine server-side processing failure (ffmpeg, storage,
                # normalization...): this is not the client's fault. Report it
                # as a 500 and keep the underlying error so it can be
                # diagnosed.
                current_app.logger.error(e, exc_info=1)
                if normalize:
                    message = "Movie preview normalization failed."
                else:
                    message = (
                        "Movie preview processing failed "
                        "(normalization disabled)."
                    )
                current_app.logger.error(message)
                deletion_service.remove_preview_file_by_id(
                    instance_id, force=True
                )
                if abort_on_failed:
                    raise PreviewProcessingFailedException(
                        message, dict={"reason": str(e)}
                    )
                return None
            preview_file = preview_files_service.update_preview_file(
                instance_id,
                {"extension": "mp4", "original_name": original_file_name},
            )
        elif extension in ALLOWED_FILE_EXTENSION:
            self.save_file_preview(instance_id, uploaded_file, extension)
            preview_file = preview_files_service.update_preview_file(
                instance_id,
                {
                    "extension": extension,
                    "original_name": original_file_name,
                    "status": "ready",
                },
            )

        if preview_file is None:
            current_app.logger.info(
                "Wrong file format, extension: %s", extension
            )
            deletion_service.remove_preview_file_by_id(instance_id)
            if abort_on_failed:
                raise WrongParameterException(
                    f"Wrong file format, extension: {extension}"
                )
        else:
            self.emit_app_preview_event(instance_id)
        return preview_file


class CreatePreviewFilePictureResource(
    BaseNewPreviewFilePicture, MethodView, ArgsMixin
):

    @jwt_required()
    @swag_from("openapi/CreatePreviewFilePictureResource_post.yml")
    def post(self, instance_id):
        """
        Create preview file
        """
        self.is_allowed(instance_id)

        if "file" not in request.files:
            raise WrongParameterException("File not provided.")

        return (
            self.process_uploaded_file(
                instance_id, request.files["file"], abort_on_failed=True
            ),
            201,
        )

    def is_allowed(self, preview_file_id):
        """
        Return true if user is allowed to add a preview.
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        if preview_file["original_name"]:
            current_app.logger.info(
                f"Reupload of an existing preview file ({preview_file_id}) not allowed."
            )
            raise PreviewFileReuploadNotAllowedException

        permissions_service.check_task_action_access(preview_file["task_id"])
        return True


class BaseBatchComment(BaseNewPreviewFilePicture, ArgsMixin):
    """
    Base class to add comments/previews/attachments.
    """

    def get_comments_args(self):
        """
        Return comments arguments.
        """
        if request.is_json:
            return self.get_args(
                [
                    {
                        "name": "comments",
                        "required": True,
                        "default": [],
                        "type": dict,
                        "action": "append",
                        "help": "List of comments to add",
                    }
                ],
            )
        else:
            args = self.get_args(
                [
                    {
                        "name": "comments",
                        "required": True,
                        "default": "[]",
                        "help": "List of comments to add",
                    }
                ],
            )
            args["comments"] = json.loads(args["comments"])
            return args

    def process_comments(self, task_id=None):
        """
        Process comments.
        """
        args = self.get_comments_args()

        if task_id is not None:
            permissions_service.check_task_action_access(task_id)

        new_comments = []
        for i, comment in enumerate(args["comments"]):
            if task_id is None:
                permissions_service.check_task_action_access(
                    comment["task_id"]
                )

            permissions_service.resolve_project_role(
                tasks_service.get_task(task_id or comment["task_id"])[
                    "project_id"
                ]
            )
            permissions_service.check_task_status_access(
                comment["task_status_id"]
            )

            if not permissions.has_manager_permissions():
                comment["person_id"] = None
                comment["created_at"] = None

            new_comment = comments_service.create_comment(
                comment.get("person_id", None),
                task_id or comment["task_id"],
                comment["task_status_id"],
                comment["text"],
                comment.get("checklist", []),
                {
                    k: v
                    for (k, v) in request.files.items()
                    if f"attachment_file-{i}" in k
                },
                comment.get("created_at", None),
                comment.get("links", []),
            )

            new_comment["preview_files"] = []
            for uploaded_preview_file in {
                k: v
                for (k, v) in request.files.items()
                if f"preview_file-{i}" in k
            }.values():
                new_preview_file = (
                    comments_service.add_preview_file_to_comment(
                        new_comment["id"],
                        new_comment["person_id"],
                        task_id or comment["task_id"],
                    )
                )
                new_preview_file = self.process_uploaded_file(
                    new_preview_file["id"],
                    uploaded_preview_file,
                    abort_on_failed=False,
                )
                if new_preview_file:
                    new_comment["preview_files"].append(new_preview_file)

            new_comments.append(new_comment)

        return new_comments, 201


class AddTaskBatchCommentResource(BaseBatchComment, MethodView):

    @jwt_required()
    @swag_from("openapi/AddTaskBatchCommentResource_post.yml")
    def post(self, task_id):
        """
        Add task batch comments
        """
        return self.process_comments(task_id)


class AddTasksBatchCommentResource(BaseBatchComment, MethodView):

    @jwt_required()
    @swag_from("openapi/AddTasksBatchCommentResource_post.yml")
    def post(self):
        """
        Add tasks batch comments
        """
        return self.process_comments()


class BasePreviewFileResource(MethodView):
    """
    Base class to download a preview file.
    """

    def __init__(self):
        MethodView.__init__(self)
        self.preview_file = None
        self.last_modified = None

    def is_allowed(self, preview_file_id):
        self.preview_file = files_service.get_preview_file_for_access(
            preview_file_id
        )
        permissions_service.check_task_access(self.preview_file["task_id"])
        self.last_modified = date_helpers.get_datetime_from_string(
            self.preview_file["updated_at"]
        )


class PreviewFileMovieResource(BasePreviewFileResource):
    """
    Allow to download a movie preview.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileMovieResource_get.yml")
    def get(self, instance_id):
        """
        Get preview movie
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id,
                last_modified=self.last_modified,
                preview_file=self.preview_file,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Movie file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class PreviewFileLowMovieResource(BasePreviewFileResource):
    """
    Allow to download a lowdef movie preview.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileLowMovieResource_get.yml")
    def get(self, instance_id):
        """
        Get preview lowdef movie
        """
        self.is_allowed(instance_id)

        try:
            # send_movie_file already falls back on the full quality version
            # then on the source.
            return send_movie_file(
                instance_id,
                lowdef=True,
                last_modified=self.last_modified,
                preview_file=self.preview_file,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Movie file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class PreviewFileSourceMovieResource(BasePreviewFileResource):
    """
    Allow to download the source movie of a preview.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileSourceMovieResource_get.yml")
    def get(self, instance_id):
        """
        Get preview source movie
        """
        self.is_allowed(instance_id)

        try:
            return send_source_movie_file(
                instance_id, last_modified=self.last_modified
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Source movie file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class PreviewFileMovieDownloadResource(BasePreviewFileResource):
    """
    Allow to download a movie preview.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileMovieDownloadResource_get.yml")
    def get(self, instance_id):
        """
        Download preview movie
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id,
                as_attachment=True,
                last_modified=self.last_modified,
                preview_file=self.preview_file,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Movie file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class PreviewFileResource(BasePreviewFileResource):
    """
    Allow to download a generic file preview.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileResource_get.yml")
    def get(self, instance_id, extension):
        """
        Get preview file
        """
        self.is_allowed(instance_id)

        try:
            extension = extension.lower()
            if (
                extension
                not in ALLOWED_PICTURE_EXTENSION | ALLOWED_FILE_EXTENSION
            ):
                raise WrongParameterException(
                    f"Extension not allowed: {extension}"
                )
            if extension == "png":
                return send_preview_picture_file(
                    "original", instance_id, last_modified=self.last_modified
                )
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_preview_standard_file(
                    instance_id,
                    extension,
                    mimetype=mimetype,
                    last_modified=self.last_modified,
                )
            else:
                return send_preview_standard_file(
                    instance_id, extension, last_modified=self.last_modified
                )

        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Non-movie file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class PreviewFileDownloadResource(BasePreviewFileResource):
    """
    Allow to download a generic file preview as attachment.
    """

    @jwt_required()
    @swag_from("openapi/PreviewFileDownloadResource_get.yml")
    def get(self, instance_id):
        """
        Download preview file
        """
        self.is_allowed(instance_id)

        extension = self.preview_file["extension"]

        try:
            if extension == "png":
                return send_preview_picture_file(
                    "original",
                    instance_id,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_preview_standard_file(
                    instance_id,
                    extension,
                    mimetype=mimetype,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
            if extension == "mp4":
                return send_movie_file(
                    instance_id,
                    as_attachment=True,
                    last_modified=self.last_modified,
                    preview_file=self.preview_file,
                )
            else:
                return send_preview_standard_file(
                    instance_id,
                    extension,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Standard file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class AttachmentThumbnailResource(MethodView):

    def __init__(self):
        MethodView.__init__(self)
        self.attachment_file = None

    def is_allowed(self, attachment_id):
        self.attachment_file = attachment_files_service.get_attachment_file(
            attachment_id
        )
        if self.attachment_file["comment_id"] is not None:
            comment = comments_service.get_comment(
                self.attachment_file["comment_id"]
            )
            permissions_service.check_task_access(comment["object_id"])
        elif self.attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                self.attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat_by_id(message["chat_id"])
            entity = entities_service.get_entity(chat["object_id"])
            permissions_service.check_project_access(entity["project_id"])
            permissions_service.check_entity_access(chat["object_id"])
        else:
            raise permissions.PermissionDenied
        return True

    @jwt_required()
    @swag_from("openapi/AttachmentThumbnailResource_get.yml")
    def get(self, attachment_file_id):
        """
        Get attachment thumbnail
        """
        self.is_allowed(attachment_file_id)

        try:
            return send_picture_file(
                "thumbnails",
                attachment_file_id,
                last_modified=date_helpers.get_datetime_from_string(
                    self.attachment_file["updated_at"]
                ),
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Picture file was not found for attachment: {attachment_file_id}"
                )
            raise PreviewFileNotFoundException


class BasePreviewPictureResource(BasePreviewFileResource):
    """
    Base class to download a thumbnail.
    """

    def __init__(self, picture_type):
        BasePreviewFileResource.__init__(self)
        self.picture_type = picture_type

    @jwt_required()
    @swag_from("openapi/BasePreviewPictureResource_get.yml")
    def get(self, instance_id):
        """
        Get preview thumbnail
        """
        self.is_allowed(instance_id)

        try:
            return send_preview_picture_file(
                self.picture_type,
                instance_id,
                last_modified=self.last_modified,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Picture file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException


class BasePreviewFileThumbnailResource(BasePreviewPictureResource):
    """
    Base class to download a thumbnail for a preview file.
    """

    def is_allowed(self, preview_file_id):
        self.preview_file = files_service.get_preview_file_for_access(
            preview_file_id
        )
        task = tasks_service.get_task(self.preview_file["task_id"])
        entity = entities_service.get_entity(task["entity_id"])
        permissions_service.resolve_project_role(task["project_id"])
        if (
            entity["preview_file_id"] != preview_file_id
            or not entity["is_shared"]
            or permissions.has_vendor_permissions()
        ):
            permissions_service.check_project_access(task["project_id"])
            permissions_service.check_entity_access(task["entity_id"])
        self.last_modified = date_helpers.get_datetime_from_string(
            self.preview_file["updated_at"]
        )


class PreviewFileThumbnailResource(BasePreviewFileThumbnailResource):

    def __init__(self):
        BasePreviewPictureResource.__init__(self, "thumbnails")


class PreviewFileTileResource(BasePreviewPictureResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "tiles")

    @jwt_required()
    @swag_from("openapi/PreviewFileTileResource_get.yml")
    def get(self, instance_id):
        """
        Get the tile sheet of a movie preview
        """
        try:
            return super().get(instance_id)
        except PreviewFileNotFoundException:
            preview_maintenance_service.generate_tile_later(instance_id)
            raise


class PreviewFilePreviewResource(BasePreviewPictureResource):
    """
    Smaller version of uploaded image.
    """

    def __init__(self):
        BasePreviewPictureResource.__init__(self, "previews")


class PreviewFileThumbnailSquareResource(BasePreviewFileThumbnailResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "thumbnails-square")


class PreviewFileOriginalResource(BasePreviewFileThumbnailResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "original")


class BaseThumbnailResource(MethodView):
    """
    Base class to post and get a thumbnail.
    """

    def __init__(
        self,
        data_type,
        get_model_func,
        update_model_func,
        size=thumbnail_utils.RECTANGLE_SIZE,
    ):
        MethodView.__init__(self)
        self.data_type = data_type
        self.get_model_func = get_model_func
        self.update_model_func = update_model_func
        self.size = size
        self.model = None
        self.last_modified = None

    def is_exist(self, instance_id):
        self.model = self.get_model_func(instance_id)

    def check_allowed_to_post(self, instance_id):
        permissions.check_admin_permissions()

    def check_allowed_to_get(self, instance_id):
        if not self.model["has_avatar"]:
            raise NotFound

    def prepare_creation(self, instance_id):
        self.model = self.update_model_func(instance_id, {"has_avatar": True})

    def emit_event(self, instance_id):
        model_name = self.data_type[:-1]
        events.emit(
            f"{model_name}:set-thumbnail",
            {f"{model_name}_id": instance_id},
        )

    @jwt_required()
    @swag_from("openapi/BaseThumbnailResource_post.yml")
    def post(self, instance_id):
        """
        Create thumbnail
        """
        self.is_exist(instance_id)
        self.check_allowed_to_post(instance_id)

        if "file" not in request.files:
            raise WrongParameterException("File not provided.")

        tmp_folder = config.TMP_DIR
        uploaded_file = request.files["file"]
        thumbnail_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        try:
            thumbnail_path = thumbnail_utils.turn_into_thumbnail(
                thumbnail_path, size=self.size
            )
            file_store.add_picture("thumbnails", instance_id, thumbnail_path)
        finally:
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)

        # Mark the avatar as present only once the thumbnail is stored, so a
        # missing/invalid file or a storage failure cannot leave has_avatar
        # set with no picture behind it (which would 404 every read).
        self.prepare_creation(instance_id)
        preview_files_service.clear_variant_from_cache(
            instance_id, "thumbnails"
        )

        thumbnail_url_path = thumbnail_utils.url_path(
            self.data_type, instance_id
        )
        self.emit_event(instance_id)
        return {"thumbnail_path": thumbnail_url_path}, 201

    @jwt_required()
    @swag_from("openapi/BaseThumbnailResource_get.yml")
    def get(self, instance_id):
        """
        Get thumbnail
        """
        self.is_exist(instance_id)
        self.check_allowed_to_get(instance_id)

        try:
            return send_picture_file(
                "thumbnails",
                instance_id,
                last_modified=date_helpers.get_datetime_from_string(
                    self.model["updated_at"]
                ),
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Thumbnail file was not found for: {instance_id}"
                )
            raise PreviewFileNotFoundException
        except IOError as e:
            current_app.logger.error(e)
            raise PreviewFileNotFoundException


class PersonThumbnailResource(BaseThumbnailResource):

    def __init__(self):
        BaseThumbnailResource.__init__(
            self,
            "persons",
            persons_service.get_person,
            persons_service.update_person,
            thumbnail_utils.BIG_SQUARE_SIZE,
        )

    def check_allowed_to_post(self, instance_id):
        permissions_service.check_person_access(instance_id)

    def prepare_creation(self, instance_id):
        self.model = self.update_model_func(
            instance_id, {"has_avatar": True}, bypass_protected_accounts=True
        )


class OrganisationThumbnailResource(BaseThumbnailResource):

    def __init__(self):
        BaseThumbnailResource.__init__(
            self,
            "organisations",
            organisation_service.get_organisation,
            organisation_service.update_organisation,
            thumbnail_utils.BIG_SQUARE_SIZE,
        )

    def is_exist(self, organisation_id):
        self.model = organisation_service.get_organisation()


class ProjectThumbnailResource(BaseThumbnailResource):
    def __init__(self):
        BaseThumbnailResource.__init__(
            self,
            "projects",
            projects_service.get_project,
            projects_service.update_project,
            thumbnail_utils.BIG_SQUARE_SIZE,
        )

    def check_allowed_to_get(self, instance_id):
        super().check_allowed_to_get(instance_id)
        if not permissions.has_manager_permissions():
            permissions_service.check_project_access(instance_id)

    def check_allowed_to_post(self, instance_id):
        return permissions_service.check_manager_project_access(instance_id)


class ReadOnlyProjectThumbnailResource(ProjectThumbnailResource):
    """
    Display url of the project thumbnail. Uploads go to the path without
    extension, so this one serves reads only and the upload permission is
    described in a single place. A post answers 405 with a pointer instead
    of falling through the routing to a misleading 404.
    """

    # flasgger only accepts a set here, a list makes /openapi.json crash
    methods = {"GET", "POST"}

    @jwt_required()
    def post(self, instance_id):
        """
        Uploads are not allowed on the display url.
        """
        return {
            "error": True,
            "message": "Upload project thumbnails on the url without "
            "extension: /pictures/thumbnails/projects/<project_id>.",
        }, 405


class SetMainPreviewResource(MethodView, ArgsMixin):
    """
    Set given preview as main preview of the related entity. This preview will
    be used to illustrate the entity.
    """

    @jwt_required()
    @swag_from("openapi/SetMainPreviewResource_put.yml")
    def put(self, preview_file_id):
        """
        Set main preview
        """
        body = validation_utils.validate_request_body(PreviewFileUploadSchema)
        frame_number = body.frame_number
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_project_access(task["project_id"])
        permissions_service.check_entity_access(task["entity_id"])
        # Clients review content but must not redefine how an entity is
        # illustrated.
        if permissions.has_client_permissions():
            raise permissions.PermissionDenied
        if frame_number is not None:
            if preview_file["extension"] != "mp4":
                raise WrongParameterException(
                    "Can't use a given frame on non movie preview"
                )
            preview_files_service.dispatch_frame_extraction(
                preview_file, frame_number, no_job=self.get_no_job()
            )
        entity = tasks_service.update_entity_preview(
            task["entity_id"],
            preview_file_id,
        )
        return entity


class UpdatePreviewPositionResource(MethodView, ArgsMixin):
    """
    Allow to change orders of previews for a single revision.
    """

    @jwt_required()
    @swag_from("openapi/UpdatePreviewPositionResource_put.yml")
    def put(self, preview_file_id):
        """
        Update preview position
        """
        body = validation_utils.validate_request_body(
            PreviewFilePositionSchema
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        permissions_service.check_task_action_access(preview_file["task_id"])
        return preview_files_service.update_preview_file_position(
            preview_file_id, body.position
        )


class UpdateAnnotationsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/UpdateAnnotationsResource_put.yml")
    def put(self, preview_file_id):
        """
        Update preview annotations
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_project_access(task["project_id"])
        is_manager = permissions.has_manager_permissions()
        is_client = permissions.has_client_permissions()
        is_supervisor_allowed = False
        if permissions.has_supervisor_permissions():
            user_departments = persons_service.get_current_user(
                relations=True
            )["departments"]
            if (
                user_departments == []
                or task_types_service.get_task_type(task["task_type_id"])[
                    "department_id"
                ]
                in user_departments
            ):
                is_supervisor_allowed = True

        if not (is_manager or is_client or is_supervisor_allowed):
            raise permissions.PermissionDenied

        body = validation_utils.validate_request_body(AnnotationsUpdateSchema)
        user = persons_service.get_current_user()
        return preview_annotations_service.update_preview_file_annotations(
            user["id"],
            task["project_id"],
            preview_file_id,
            additions=body.additions,
            updates=body.updates,
            deletions=body.deletions,
        )


class RunningPreviewFiles(MethodView, ArgsMixin):
    """
    Retrieve all preview files from open productions with states equals
    to processing or broken
    """

    @jwt_required()
    @swag_from("openapi/RunningPreviewFiles_get.yml")
    def get(self):
        """
        Get running preview files
        """
        permissions.check_admin_permissions()
        args = self.get_args(
            [
                ("cursor_preview_file_id", None, False),
                ("limit", None, False, int),
            ],
        )
        cursor_preview_file_id = args["cursor_preview_file_id"]
        limit = args["limit"]

        if cursor_preview_file_id is not None and not fields.is_valid_id(
            cursor_preview_file_id
        ):
            raise WrongParameterException(
                "The cursor_preview_file_id parameter is not a valid id"
            )

        return preview_files_service.get_running_preview_files(
            cursor_preview_file_id=cursor_preview_file_id,
            limit=limit,
        )


class ExtractFrameFromPreview(MethodView, ArgsMixin):
    """
    Extract the current frame of the preview
    """

    @jwt_required()
    @swag_from("openapi/ExtractFrameFromPreview_get.yml")
    def get(self, preview_file_id):
        """
        Extract frame from preview
        """
        args = self.get_args([("frame_number", 0, False, int)])
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_manager_project_access(task["project_id"])
        extracted_frame_path = (
            preview_files_service.extract_frame_from_preview_file(
                preview_file, args["frame_number"]
            )
        )
        if extracted_frame_path is None:
            return {"error": "preview file binary is not available"}, 404
        try:
            return flask_send_file(
                extracted_frame_path,
                conditional=True,
                mimetype="image/png",
                as_attachment=False,
                download_name=os.path.basename(extracted_frame_path),
            )
        finally:
            os.remove(extracted_frame_path)


class ExtractAnnotatedFrameFromPreview(MethodView):
    """
    Extract a frame (movie) or the picture itself, with its matching
    annotation rendered on top.
    """

    @jwt_required()
    @swag_from("openapi/ExtractAnnotatedFrameFromPreview_get.yml")
    def get(self, preview_file_id):
        """
        Extract annotated frame from preview
        """
        args = validation_utils.validate_request_body(
            ExtractAnnotatedFrameSchema
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_manager_project_access(task["project_id"])
        extracted_frame_path = preview_annotations_service.extract_annotation_frame_from_preview_file(
            preview_file, args.frame_number
        )
        if extracted_frame_path is None:
            return {"error": "preview file binary is not available"}, 404
        try:
            return flask_send_file(
                extracted_frame_path,
                conditional=True,
                mimetype="image/png",
                as_attachment=False,
                download_name=os.path.basename(extracted_frame_path),
            )
        finally:
            os.remove(extracted_frame_path)


def _serve_annotated_frames_bundle(
    preview_file_id, build_bundle, mimetype, file_extension
):
    """
    Common flow for the zip and pdf bulk-download resources: check
    permissions, build the bundle via the service, send it as an
    attachment named `{preview_base_name}_annotated_frames.{ext}`.
    """
    preview_file = files_service.get_preview_file(preview_file_id)
    task = tasks_service.get_task(preview_file["task_id"])
    permissions_service.check_manager_project_access(task["project_id"])
    bundle_path = build_bundle(preview_file)
    if bundle_path is None:
        return {"error": "preview file binary is not available"}, 404
    base_name = os.path.splitext(
        preview_files_service.get_preview_file_name(preview_file_id)
    )[0]
    download_name = f"{base_name}_annotated_frames.{file_extension}"
    try:
        return flask_send_file(
            bundle_path,
            conditional=True,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name,
        )
    finally:
        os.remove(bundle_path)


class ExtractAllAnnotatedFramesFromPreview(MethodView):
    """
    Build a zip archive containing every annotated frame (movie) or
    every annotated copy of the picture preview.
    """

    @jwt_required()
    @swag_from("openapi/ExtractAllAnnotatedFramesFromPreview_get.yml")
    def get(self, preview_file_id):
        """
        Extract all annotated frames from preview as a zip
        """
        return _serve_annotated_frames_bundle(
            preview_file_id,
            preview_annotations_service.extract_all_annotation_frames_from_preview_file,
            mimetype="application/zip",
            file_extension="zip",
        )


class ExtractAllAnnotatedFramesAsPdfFromPreview(MethodView):
    """
    Build a multi-page PDF containing every annotated frame (movie) or
    every annotated copy of the picture preview.
    """

    @jwt_required()
    @swag_from("openapi/ExtractAllAnnotatedFramesAsPdfFromPreview_get.yml")
    def get(self, preview_file_id):
        """
        Extract all annotated frames from preview as a PDF
        """
        return _serve_annotated_frames_bundle(
            preview_file_id,
            preview_annotations_service.extract_all_annotation_frames_pdf_from_preview_file,
            mimetype="application/pdf",
            file_extension="pdf",
        )


class ExtractTileFromPreview(MethodView):
    """
    Extract a tile from a preview_file
    """

    @jwt_required()
    @swag_from("openapi/ExtractTileFromPreview_get.yml")
    def get(self, preview_file_id):
        """
        Extract tile from preview
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        permissions_service.check_task_access(preview_file["task_id"])
        extracted_tile_path = (
            preview_files_service.extract_tile_from_preview_file(preview_file)
        )
        if extracted_tile_path is None:
            return {"error": "preview file binary is not available"}, 404
        file_store.add_picture("tiles", preview_file_id, extracted_tile_path)
        preview_file_states_service.record_file_state(
            preview_file_id,
            "pictures",
            "tiles",
            preview_file_states_service.OK,
        )
        try:
            return flask_send_file(
                extracted_tile_path,
                conditional=True,
                mimetype="image/png",
                as_attachment=False,
                download_name=os.path.basename(extracted_tile_path),
            )
        finally:
            os.remove(extracted_tile_path)


class CreatePreviewBackgroundFileResource(MethodView):
    """
    Main resource to add a preview background file. It stores the preview background
    file and generates a rectangle thumbnail.
    """

    @jwt_required()
    @swag_from("openapi/CreatePreviewBackgroundFileResource_post.yml")
    def post(self, instance_id):
        """
        Create preview background file
        """
        self.check_permissions(instance_id)

        preview_background_file = files_service.get_preview_background_file(
            instance_id
        )

        if "file" not in request.files:
            raise WrongParameterException("File not provided.")

        uploaded_file = request.files["file"]

        file_name_parts = uploaded_file.filename.split(".")
        extension = file_name_parts.pop().lower()
        original_file_name = ".".join(file_name_parts)

        if extension in ALLOWED_PREVIEW_BACKGROUND_EXTENSION:
            metadata = self.save_preview_background_file(
                instance_id, uploaded_file, extension
            )
            preview_background_file = (
                files_service.update_preview_background_file(
                    instance_id,
                    {
                        "extension": extension,
                        "original_name": original_file_name,
                        "file_size": metadata["file_size"],
                    },
                )
            )
            files_service.clear_preview_background_file_cache(instance_id)
            self.emit_preview_background_file_event(preview_background_file)
            return preview_background_file, 201

        else:
            current_app.logger.info(
                f"Wrong file format, extension: {extension}"
            )
            deletion_service.remove_preview_background_file_by_id(
                instance_id, force=True
            )
            raise WrongParameterException(
                f"Wrong file format, extension: {extension}"
            )

    def check_permissions(self, instance_id):
        """
        Check if user has permissions to add a preview background file.
        """
        return permissions.check_admin_permissions()

    def save_preview_background_file(
        self, instance_id, uploaded_file, extension
    ):
        """
        Get uploaded preview background file, build thumbnail then save
        everything in the file storage.
        """
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
            preview_files_service.clear_variant_from_cache(
                instance_id, "preview-backgrounds", extension
            )
            if extension == "hdr":
                thumbnail_path = thumbnail_utils.turn_hdr_into_thumbnail(
                    preview_background_path
                )
                file_store.add_picture(
                    "thumbnails", instance_id, thumbnail_path
                )
                preview_files_service.clear_variant_from_cache(
                    instance_id, "thumbnails"
                )

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

    def emit_preview_background_file_event(self, preview_background_file):
        """
        Emit an event, each time a preview background file is added.
        """
        events.emit(
            "preview-background-file:update",
            {"preview_background_file_id": preview_background_file["id"]},
        )
        events.emit(
            "preview-background-file:add-file",
            {
                "preview_background_file_id": preview_background_file["id"],
                "extension": preview_background_file["extension"],
            },
        )


class PreviewBackgroundFileResource(MethodView):
    """
    Main resource to download a preview background file.
    """

    @jwt_required()
    @swag_from("openapi/PreviewBackgroundFileResource_get.yml")
    def get(self, instance_id, extension):
        """
        Get preview background file
        """
        preview_background_file = files_service.get_preview_background_file(
            instance_id
        )

        extension = extension.lower()
        if preview_background_file["extension"] != extension:
            raise PreviewBackgroundFileNotFoundException

        try:
            return send_picture_file(
                "preview-backgrounds",
                instance_id,
                extension=extension,
                download_name=f"{preview_background_file['original_name']}.{extension}",
                last_modified=date_helpers.get_datetime_from_string(
                    preview_background_file["updated_at"]
                ),
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Preview background file was not found for: {instance_id}"
                )
            raise PreviewBackgroundFileNotFoundException


class PreviewBackgroundFileThumbnailResource(BaseThumbnailResource):
    def __init__(self):
        BaseThumbnailResource.__init__(
            self,
            "preview-backgrounds",
            files_service.get_preview_background_file,
            files_service.update_preview_background_file,
        )

    def check_allowed_to_get(self, preview_background_file_id):
        return True

    @jwt_required()
    def post(self, preview_background_file_id):
        """
        Uploads are not allowed on the display url.
        """
        # Raising AttributeError here used to surface as an anonymous 500.
        return {
            "error": True,
            "message": "Preview backgrounds are uploaded through "
            "/pictures/preview-background-files/<preview_background_file_id>.",
        }, 405
