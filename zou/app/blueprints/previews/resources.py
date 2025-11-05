import os
import orjson as json

from flask import abort, request, current_app
from flask import send_file as flask_send_file
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from flask_fs.errors import FileNotFound
from werkzeug.exceptions import NotFound

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.stores import file_store
from zou.app.services import (
    comments_service,
    chats_service,
    deletion_service,
    entities_service,
    files_service,
    names_service,
    persons_service,
    projects_service,
    preview_files_service,
    tasks_service,
    user_service,
)
from zou.app.stores import queue_store
from zou.utils import movie
from zou.app.utils import (
    fs,
    events,
    permissions,
    thumbnail as thumbnail_utils,
    date_helpers,
)
from zou.app.services.exception import (
    WrongParameterException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileReuploadNotAllowedException,
)


ALLOWED_PICTURE_EXTENSION = ["jpe", "jpeg", "jpg", "png"]
ALLOWED_MOVIE_EXTENSION = [
    "avi",
    "m4v",
    "mkv",
    "mov",
    "mp4",
    "webm",
    "wmv",
]
ALLOWED_FILE_EXTENSION = [
    "ae",
    "ai",
    "blend",
    "clip",
    "comp",
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
]
ALLOWED_PREVIEW_BACKGROUND_EXTENSION = ["hdr"]


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


def send_movie_file(
    preview_file_id, as_attachment=False, lowdef=False, last_modified=None
):
    folder = "previews"
    if lowdef:
        folder = "lowdef"
    return send_storage_file(
        file_store.get_local_movie_path,
        file_store.open_movie,
        folder,
        preview_file_id,
        "mp4",
        mimetype="video/mp4",
        as_attachment=as_attachment,
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
):
    """
    Send file from storage. If it's not a local storage, cache the file in
    a temporary folder before sending it. It accepts conditional headers.
    """
    file_size = None
    try:
        if prefix in ["movies", "original", "preview-backgrounds"]:
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
    file_path = fs.get_file_path_and_file(
        config,
        get_local_path,
        open_file,
        prefix,
        preview_file_id,
        extension,
        file_size=file_size,
    )

    if as_attachment:
        download_name = names_service.get_preview_file_name(preview_file_id)

    try:
        return flask_send_file(
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


class BaseNewPreviewFilePicture:
    """
    Base class to add previews.
    """

    def save_picture_preview(self, instance_id, uploaded_file):
        """
        Get uploaded picture, build thumbnails then save everything in the file
        storage.
        """
        tmp_folder = config.TMP_DIR
        original_tmp_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        file_size = fs.get_file_size(original_tmp_path)
        width, height = thumbnail_utils.get_dimensions(original_tmp_path)
        preview_files_service.save_variants(instance_id, original_tmp_path)
        return {
            "preview_file_id": instance_id,
            "file_size": file_size,
            "extension": "png",
            "width": width,
            "height": height,
        }

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
        if normalize and config.ENABLE_JOB_QUEUE and not no_job:
            queue_store.job_queue.enqueue(
                preview_files_service.prepare_and_store_movie,
                args=(preview_file_id, uploaded_movie_path),
                job_timeout=int(config.JOB_QUEUE_TIMEOUT),
            )
        else:
            preview_files_service.prepare_and_store_movie(
                preview_file_id, uploaded_movie_path, normalize=normalize
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
        file_store.add_file("previews", instance_id, file_path)
        file_size = fs.get_file_size(file_path)
        preview_files_service.update_preview_file(
            instance_id, {"file_size": file_size}, silent=True
        )
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
                {"comment_id": comment_id},
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
            metadada = self.save_picture_preview(instance_id, uploaded_file)
            preview_file = preview_files_service.update_preview_file(
                instance_id,
                {
                    "extension": "png",
                    "original_name": original_file_name,
                    "width": metadada["width"],
                    "height": metadada["height"],
                    "file_size": metadada["file_size"],
                    "status": "ready",
                },
            )
            tasks_service.update_preview_file_info(preview_file)
        elif extension in ALLOWED_MOVIE_EXTENSION:
            try:
                normalize = self.get_bool_parameter("normalize", "true")
                self.save_movie_preview(instance_id, uploaded_file, normalize)
            except Exception as e:
                current_app.logger.error(e, exc_info=1)
                current_app.logger.error("Normalization failed.")
                deletion_service.remove_preview_file_by_id(
                    instance_id, force=True
                )
                if abort_on_failed:
                    abort(400, "Normalization failed.")
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
                abort(400, "Wrong file format, extension: %s" % extension)
        else:
            self.emit_app_preview_event(instance_id)
        return preview_file


class CreatePreviewFilePictureResource(
    BaseNewPreviewFilePicture, Resource, ArgsMixin
):

    @jwt_required()
    def post(self, instance_id):
        """
        Create preview file
        ---
        description: Main resource to add a preview. It stores the preview file
          and generates three picture files (thumbnails) matching preview when
          it's possible, a square thumbnail, a rectangle thumbnail and a
          midsize file.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: true
            type: file
            description: Preview file to upload
        responses:
          201:
            description: Preview file added successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Preview file unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    extension:
                      type: string
                      description: File extension
                      example: "png"
                    file_size:
                      type: integer
                      description: File size in bytes
                      example: 1024000
          400:
            description: Wrong file format or normalization failed
        """
        self.is_exist(instance_id)
        self.is_allowed(instance_id)

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
                f"Reupload of an existing preview file ({preview_file_id} not allowed."
            )
            raise PreviewFileReuploadNotAllowedException

        user_service.check_task_action_access(preview_file["task_id"])
        return True

    def is_exist(self, preview_file_id):
        """
        Return true if preview file entry matching given id exists in database.
        """
        return files_service.get_preview_file(preview_file_id) is not None


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
            user_service.check_task_action_access(task_id)

        new_comments = []
        for i, comment in enumerate(args["comments"]):
            user_service.check_task_status_access(comment["task_status_id"])

            if task_id is None:
                user_service.check_task_action_access(comment["task_id"])

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
                new_preview_file = tasks_service.add_preview_file_to_comment(
                    new_comment["id"],
                    new_comment["person_id"],
                    task_id or comment["task_id"],
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


class AddTaskBatchCommentResource(BaseBatchComment, Resource):

    @jwt_required()
    def post(self, task_id):
        """
        Add task batch comments
        ---
        description: Creates new comments for given task. Each comment requires
          a text, a task_status and a person as arguments. Can include preview
          files and attachments.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            schema:
              type: string
              format: uuid
            description: Task unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                required:
                  - comments
                properties:
                  comments:
                    type: string
                    description: JSON string containing array of comments
                    example: '[{"text": "Good work", "task_status_id": "uuid"}]'
        responses:
          201:
            description: New comments created
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        return self.process_comments(task_id)


class AddTasksBatchCommentResource(BaseBatchComment, Resource):

    @jwt_required()
    def post(self):
        """
        Add tasks batch comments
        ---
        description: Creates new comments for given tasks. Each comment requires
          a task_id, text, a task_status and a person as arguments. Can include
          preview files and attachments.
        tags:
          - Comments
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                required:
                  - comments
                properties:
                  comments:
                    type: string
                    description: JSON string containing array of comments
                    example: '[{"task_id": "uuid", "text": "Good work", "task_status_id": "uuid"}]'
        responses:
          201:
            description: New comments created
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
        """
        return self.process_comments()


class BasePreviewFileResource(Resource):
    """
    Base class to download a preview file.
    """

    def __init__(self):
        Resource.__init__(self)
        self.preview_file = None
        self.last_modified = None

    def is_allowed(self, preview_file_id):
        self.preview_file = files_service.get_preview_file(preview_file_id)
        user_service.check_task_access(self.preview_file["task_id"])
        self.last_modified = date_helpers.get_datetime_from_string(
            self.preview_file["updated_at"]
        )


class PreviewFileMovieResource(BasePreviewFileResource):
    """
    Allow to download a movie preview.
    """

    @jwt_required()
    def get(self, instance_id):
        """
        Get preview movie
        ---
        description: Download a movie preview file.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Movie preview downloaded
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id, last_modified=self.last_modified
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    "Movie file was not found for: %s" % instance_id
                )
            abort(404)


class PreviewFileLowMovieResource(BasePreviewFileResource):
    """
    Allow to download a lowdef movie preview.
    """

    @jwt_required()
    def get(self, instance_id):
        """
        Get preview lowdef movie
        ---
        description: Download a low definition movie preview file. Falls back to
          full quality if lowdef version is not available.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Low definition movie preview downloaded
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id, lowdef=True, last_modified=self.last_modified
            )
        except Exception:
            try:
                return send_movie_file(
                    instance_id, last_modified=self.last_modified
                )
            except FileNotFound:
                if config.LOG_FILE_NOT_FOUND:
                    current_app.logger.error(
                        "Movie file was not found for: %s" % instance_id
                    )
                abort(404)


class PreviewFileMovieDownloadResource(BasePreviewFileResource):
    """
    Allow to download a movie preview.
    """

    @jwt_required()
    def get(self, instance_id):
        """
        Download preview movie
        ---
        description: Download a movie preview file as attachment.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Movie preview downloaded as attachment
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id,
                as_attachment=True,
                last_modified=self.last_modified,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    "Movie file was not found for: %s" % instance_id
                )
            abort(404)


class PreviewFileResource(BasePreviewFileResource):
    """
    Allow to download a generic file preview.
    """

    @jwt_required()
    def get(self, instance_id, extension):
        """
        Get preview file
        ---
        description: Download a generic file preview by extension.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: extension
            required: true
            schema:
              type: string
            description: File extension
            example: png
        responses:
          200:
            description: Generic file preview downloaded
            content:
              application/octet-stream:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        try:
            extension = extension.lower()
            if extension == "png":
                return send_picture_file(
                    "original", instance_id, last_modified=self.last_modified
                )
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_standard_file(
                    instance_id,
                    extension,
                    mimetype,
                    last_modified=self.last_modified,
                )
            else:
                return send_standard_file(
                    instance_id, extension, last_modified=self.last_modified
                )

        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    "Non-movie file was not found for: %s" % instance_id
                )
            abort(404)


class PreviewFileDownloadResource(BasePreviewFileResource):
    """
    Allow to download a generic file preview as attachment.
    """

    @jwt_required()
    def get(self, instance_id):
        """
        Download preview file
        ---
        description: Download a generic file preview as attachment.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Generic file preview downloaded as attachment
            content:
              application/octet-stream:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        extension = self.preview_file["extension"]

        try:
            if extension == "png":
                return send_picture_file(
                    "original",
                    instance_id,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_standard_file(
                    instance_id,
                    extension,
                    mimetype,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
            if extension == "mp4":
                return send_picture_file(
                    "original",
                    instance_id,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
            else:
                return send_standard_file(
                    instance_id,
                    extension,
                    as_attachment=True,
                    last_modified=self.last_modified,
                )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    "Standard file was not found for: %s" % instance_id
                )
            abort(404)


class AttachmentThumbnailResource(Resource):

    def __init__(self):
        Resource.__init__(self)
        self.attachment_file = None

    def is_allowed(self, attachment_id):
        self.attachment_file = comments_service.get_attachment_file(
            attachment_id
        )
        if self.attachment_file["comment_id"] is not None:
            comment = tasks_service.get_comment(
                self.attachment_file["comment_id"]
            )
            user_service.check_task_access(comment["object_id"])
        elif self.attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                self.attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat_by_id(message["chat_id"])
            entity = entities_service.get_entity(chat["object_id"])
            user_service.check_project_access(entity["project_id"])
            user_service.check_entity_access(chat["object_id"])
        else:
            raise permissions.PermissionDenied
        return True

    @jwt_required()
    def get(self, attachment_file_id):
        """
        Get attachment thumbnail
        ---
        description: Download the thumbnail representing given attachment file.
        tags:
          - Previews
        parameters:
          - in: path
            name: attachment_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Attachment file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Attachment thumbnail downloaded
            content:
              image/png:
                schema:
                  type: string
                  format: binary
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
                    "Picture file was not found for attachment: %s"
                    % (attachment_file_id)
                )
            abort(404)


class BasePreviewPictureResource(BasePreviewFileResource):
    """
    Base class to download a thumbnail.
    """

    def __init__(self, picture_type):
        BasePreviewFileResource.__init__(self)
        self.picture_type = picture_type

    @jwt_required()
    def get(self, instance_id):
        """
        Get preview thumbnail
        ---
        description: Download a thumbnail for a preview file.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Preview thumbnail downloaded
            content:
              image/png:
                schema:
                  type: string
                  format: binary
        """
        self.is_allowed(instance_id)

        try:
            return send_picture_file(
                self.picture_type,
                instance_id,
                last_modified=self.last_modified,
            )
        except FileNotFound:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    "Picture file was not found for: %s" % instance_id
                )
            abort(404)


class BasePreviewFileThumbnailResource(BasePreviewPictureResource):
    """
    Base class to download a thumbnail for a preview file.
    """

    def is_allowed(self, preview_file_id):
        self.preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(self.preview_file["task_id"])
        entity = entities_service.get_entity(task["entity_id"])
        if (
            entity["preview_file_id"] != preview_file_id
            or not entity["is_shared"]
            or permissions.has_vendor_permissions()
        ):
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
        self.last_modified = date_helpers.get_datetime_from_string(
            self.preview_file["updated_at"]
        )


class PreviewFileThumbnailResource(BasePreviewFileThumbnailResource):

    def __init__(self):
        BasePreviewPictureResource.__init__(self, "thumbnails")


class PreviewFileTileResource(BasePreviewPictureResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "tiles")


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


class BaseThumbnailResource(Resource):
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
        Resource.__init__(self)
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
            "%s:set-thumbnail" % model_name,
            {"%s_id" % model_name: instance_id},
        )

    @jwt_required()
    def post(self, instance_id):
        """
        Create thumbnail
        ---
        description: Create a thumbnail for given object instance.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Object instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: true
            type: file
            description: Image file to use as thumbnail
        responses:
          201:
            description: Thumbnail created successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    thumbnail_path:
                      type: string
                      description: URL path to the thumbnail
                      example: "/api/thumbnails/persons/uuid"
        """
        self.is_exist(instance_id)
        self.check_allowed_to_post(instance_id)

        self.prepare_creation(instance_id)

        tmp_folder = config.TMP_DIR
        uploaded_file = request.files["file"]
        thumbnail_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        thumbnail_path = thumbnail_utils.turn_into_thumbnail(
            thumbnail_path, size=self.size
        )
        file_store.add_picture("thumbnails", instance_id, thumbnail_path)
        os.remove(thumbnail_path)
        preview_files_service.clear_variant_from_cache(
            instance_id, "thumbnails"
        )

        thumbnail_url_path = thumbnail_utils.url_path(
            self.data_type, instance_id
        )
        self.emit_event(instance_id)
        return {"thumbnail_path": thumbnail_url_path}, 201

    @jwt_required()
    def get(self, instance_id):
        """
        Get thumbnail
        ---
        description: Download the thumbnail linked to given object instance.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Object instance unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Thumbnail downloaded
            content:
              image/png:
                schema:
                  type: string
                  format: binary
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
                    "Thumbnail file was not found for: %s" % instance_id
                )
            abort(404)
        except IOError as e:
            current_app.logger.error(e)
            abort(404)


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
        user_service.check_person_access(instance_id)

    def prepare_creation(self, instance_id):
        self.model = self.update_model_func(
            instance_id, {"has_avatar": True}, bypass_protected_accounts=True
        )


class CreatePersonThumbnailResource(PersonThumbnailResource):
    pass


class OrganisationThumbnailResource(BaseThumbnailResource):

    def __init__(self):
        BaseThumbnailResource.__init__(
            self,
            "organisations",
            persons_service.get_organisation,
            persons_service.update_organisation,
            thumbnail_utils.BIG_SQUARE_SIZE,
        )

    def is_exist(self, organisation_id):
        self.model = persons_service.get_organisation()


class CreateOrganisationThumbnailResource(OrganisationThumbnailResource):
    pass


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
            user_service.check_project_access(instance_id)


class CreateProjectThumbnailResource(ProjectThumbnailResource):

    def check_allowed_to_post(self, instance_id):
        return user_service.check_manager_project_access(instance_id)


class SetMainPreviewResource(Resource, ArgsMixin):
    """
    Set given preview as main preview of the related entity. This preview will
    be used to illustrate the entity.
    """

    @jwt_required()
    def put(self, preview_file_id):
        """
        Set main preview
        ---
        description: Set given preview as main preview of the related entity.
          This preview will be used to illustrate the entity.
        tags:
          - Previews
        parameters:
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: frame_number
            required: false
            schema:
              type: integer
            description: Frame number for movie previews
            example: 120
        responses:
          200:
            description: Preview set as main preview
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Entity unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    preview_file_id:
                      type: string
                      format: uuid
                      description: Preview file unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
          400:
            description: Cannot use frame number on non-movie preview
        """
        args = self.get_args([("frame_number", None, False, int)])
        frame_number = args["frame_number"]
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        if frame_number is not None:
            if preview_file["extension"] != "mp4":
                raise WrongParameterException(
                    "Can't use a given frame on non movie preview"
                )
            preview_files_service.replace_extracted_frame_for_preview_file(
                preview_file, frame_number
            )
        entity = entities_service.update_entity_preview(
            task["entity_id"],
            preview_file_id,
        )
        return entity


class UpdatePreviewPositionResource(Resource, ArgsMixin):
    """
    Allow to change orders of previews for a single revision.
    """

    @jwt_required()
    def put(self, preview_file_id):
        """
        Update preview position
        ---
        description: Allow to change orders of previews for a single revision.
        tags:
          - Previews
        parameters:
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  position:
                    type: integer
                    description: New position for the preview
                    example: 2
        responses:
          200:
            description: Preview position updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Preview file unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    position:
                      type: integer
                      description: Preview position
                      example: 2
        """
        args = self.get_args([{"name": "position", "default": 0, "type": int}])
        preview_file = files_service.get_preview_file(preview_file_id)
        user_service.check_task_action_access(preview_file["task_id"])
        return preview_files_service.update_preview_file_position(
            preview_file_id, args["position"]
        )


class UpdateAnnotationsResource(Resource, ArgsMixin):

    @jwt_required()
    def put(self, preview_file_id):
        """
        Update preview annotations
        ---
        description: Allow to modify the annotations stored at the preview level.
          Modifications are applied via three fields, additions to give all the
          annotations that need to be added, updates that list annotations that
          needs to be modified, and deletions to list the IDs of annotations that
          needs to be removed.
        tags:
          - Previews
        parameters:
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  additions:
                    type: array
                    description: Annotations to add
                    items:
                      type: object
                    example: [{"type": "drawing", "x": 100, "y": 200}]
                  updates:
                    type: array
                    description: Annotations to update
                    items:
                      type: object
                    example: [{"id": "uuid", "x": 150, "y": 250}]
                  deletions:
                    type: array
                    description: Annotation IDs to remove
                    items:
                      type: string
                      format: uuid
                    example: ["a24a6ea4-ce75-4665-a070-57453082c25"]
        responses:
          200:
            description: Preview annotations updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Preview file unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    annotations:
                      type: array
                      description: Updated annotations
                      items:
                        type: object
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        is_manager = permissions.has_manager_permissions()
        is_client = permissions.has_client_permissions()
        is_supervisor_allowed = False
        if permissions.has_supervisor_permissions():
            user_departments = persons_service.get_current_user(
                relations=True
            )["departments"]
            if (
                user_departments == []
                or tasks_service.get_task_type(task["task_type_id"])[
                    "department_id"
                ]
                in user_departments
            ):
                is_supervisor_allowed = True

        if not (is_manager or is_client or is_supervisor_allowed):
            raise permissions.PermissionDenied

        additions = request.json.get("additions", [])
        updates = request.json.get("updates", [])
        deletions = request.json.get("deletions", [])
        user = persons_service.get_current_user()
        return preview_files_service.update_preview_file_annotations(
            user["id"],
            task["project_id"],
            preview_file_id,
            additions=additions,
            updates=updates,
            deletions=deletions,
        )


class RunningPreviewFiles(Resource, ArgsMixin):
    """
    Retrieve all preview files from open productions with states equals
    to processing or broken
    """

    @jwt_required()
    def get(self):
        """
        Get running preview files
        ---
        description: Retrieve all preview files from open productions with
          states equal to processing or broken.
        tags:
          - Previews
        responses:
          200:
            description: All preview files from open productions with processing or broken states
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Preview file unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      status:
                        type: string
                        description: Preview file status
                        example: "processing"
        """
        permissions.check_admin_permissions()
        return preview_files_service.get_running_preview_files()


class ExtractFrameFromPreview(Resource, ArgsMixin):
    """
    Extract the current frame of the preview
    """

    @jwt_required()
    def get(self, preview_file_id):
        """
        Extract frame from preview
        ---
        description: Extract a frame from a preview file movie. Frame number can
          be specified as query parameter, defaults to 0.
        tags:
          - Previews
        parameters:
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: frame_number
            required: false
            schema:
              type: integer
            description: Frame number to extract
            example: 120
        responses:
          200:
            description: Extracted frame as PNG image
            content:
              image/png:
                schema:
                  type: string
                  format: binary
        """
        args = self.get_args([("frame_number", 0, False, int)])
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_manager_project_access(task["project_id"])
        extracted_frame_path = (
            preview_files_service.extract_frame_from_preview_file(
                preview_file, args["frame_number"]
            )
        )
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


class ExtractTileFromPreview(Resource):
    """
    Extract a tile from a preview_file
    """

    @jwt_required()
    def get(self, preview_file_id):
        """
        Extract tile from preview
        ---
        description: Extract a tile from a preview file movie.
        tags:
          - Previews
        parameters:
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Extracted tile as PNG image
            content:
              image/png:
                schema:
                  type: string
                  format: binary
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        user_service.check_task_access(preview_file["task_id"])
        extracted_tile_path = (
            preview_files_service.extract_tile_from_preview_file(preview_file)
        )
        file_store.add_picture("tiles", preview_file_id, extracted_tile_path)
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


class CreatePreviewBackgroundFileResource(Resource):
    """
    Main resource to add a preview background file. It stores the preview background
    file and generates a rectangle thumbnail.
    """

    @jwt_required()
    def post(self, instance_id):
        """
        Create preview background file
        ---
        description: Main resource to add a preview background file. It stores
          the preview background file and generates a rectangle thumbnail.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview background file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: true
            type: file
            description: HDR file to upload
        responses:
          201:
            description: Preview background file added successfully
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Preview background file unique identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    extension:
                      type: string
                      description: File extension
                      example: "hdr"
                    file_size:
                      type: integer
                      description: File size in bytes
                      example: 2048000
          400:
            description: Wrong file format or error saving file
        """
        self.check_permissions(instance_id)

        preview_background_file = files_service.get_preview_background_file(
            instance_id
        )

        uploaded_file = request.files["file"]

        file_name_parts = uploaded_file.filename.split(".")
        extension = file_name_parts.pop().lower()
        original_file_name = ".".join(file_name_parts)

        if extension in ALLOWED_PREVIEW_BACKGROUND_EXTENSION:
            metadada = self.save_preview_background_file(
                instance_id, uploaded_file, extension
            )
            preview_background_file = (
                files_service.update_preview_background_file(
                    instance_id,
                    {
                        "extension": extension,
                        "original_name": original_file_name,
                        "file_size": metadada["file_size"],
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
            abort(400, f"Wrong file format, extension: {extension}")

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
        except:
            current_app.logger.error(
                f"Error while saving preview background file and thumbnail: {instance_id}"
            )
            deletion_service.remove_preview_background_file_by_id(
                instance_id, force=True
            )
            abort(
                400,
                f"Error while saving preview background file and thumbnail: {instance_id}",
            )
        finally:
            try:
                if os.path.exists(preview_background_path):
                    os.remove(preview_background_path)
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
            except:
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


class PreviewBackgroundFileResource(Resource):
    """
    Main resource to download a preview background file.
    """

    @jwt_required()
    def get(self, instance_id, extension):
        """
        Get preview background file
        ---
        description: Download a preview background file.
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview background file unique identifier
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: extension
            required: true
            schema:
              type: string
            description: File extension
            example: hdr
        responses:
          200:
            description: Preview background file downloaded
            content:
              image/vnd.radiance:
                schema:
                  type: string
                  format: binary
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
                    "Preview background file was not found for: %s"
                    % instance_id
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

    def post(self, preview_background_file_id):
        raise AttributeError("Method not allowed")
