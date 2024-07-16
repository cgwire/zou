import os

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
    assets_service,
    comments_service,
    chats_service,
    deletion_service,
    entities_service,
    files_service,
    names_service,
    persons_service,
    projects_service,
    preview_files_service,
    shots_service,
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
    ArgumentsException,
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
    "ma",
    "mb",
    "mp3",
    "obj",
    "pdf",
    "psd",
    "psb",
    "rar",
    "sbbkp",
    "svg",
    "swf",
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


class CreatePreviewFilePictureResource(Resource, ArgsMixin):
    """
    Main resource to add a preview. It stores the preview file and generates
    three picture files matching preview when it's possible: a square thumbnail,
    a rectangle thumbnail and a midsize file.
    """

    @jwt_required()
    def post(self, instance_id):
        """
        Main resource to add a preview.
        ---
        tags:
          - Previews
        description: "It stores the preview file and generates three picture files matching preview when it's possible: a square thumbnail, a rectangle thumbnail and a midsize file."
        consumes:
          - multipart/form-data
          - image/png
          - application/pdf
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: True
            type: file
        responses:
            200:
                description: Preview added
        """
        if not self.is_exist(instance_id):
            abort(404)

        if not self.is_allowed(instance_id):
            abort(403)

        uploaded_file = request.files["file"]

        file_name_parts = uploaded_file.filename.split(".")
        extension = file_name_parts.pop().lower()
        original_file_name = ".".join(file_name_parts)

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
            self.emit_app_preview_event(instance_id)
            return preview_file, 201

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
                abort(400, "Normalization failed.")
            preview_file = preview_files_service.update_preview_file(
                instance_id,
                {"extension": "mp4", "original_name": original_file_name},
            )
            self.emit_app_preview_event(instance_id)
            return preview_file, 201

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
            self.emit_app_preview_event(instance_id)
            return preview_file, 201

        else:
            current_app.logger.info(
                "Wrong file format, extension: %s", extension
            )
            deletion_service.remove_preview_file_by_id(instance_id)
            abort(400, "Wrong file format, extension: %s" % extension)

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

        task = tasks_service.get_task(preview_file["task_id"])
        try:
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
            return True
        except permissions.PermissionDenied:
            return False

    def is_exist(self, preview_file_id):
        """
        Return true if preview file entry matching given id exists in database.
        """
        return files_service.get_preview_file(preview_file_id) is not None


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
        task = tasks_service.get_task(self.preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
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
        Download a movie preview.
        ---
        tags:
          - Previews
        description: "It stores the preview file and generates three picture files matching preview when it's possible: a square thumbnail, a rectangle thumbnail and a midsize file."
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Movie preview downloaded
            403:
                description: Instance not allowed
            404:
                description: File not found
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id, last_modified=self.last_modified
            )
        except FileNotFound:
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
        Download a lowdef movie preview.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Lowdef movie preview downloaded
            403:
                description: Instance not allowed
            404:
                description: File not found
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
        Download a movie preview.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Movie preview downloaded
            403:
                description: Instance not allowed
            404:
                description: File not found
        """
        self.is_allowed(instance_id)

        try:
            return send_movie_file(
                instance_id,
                as_attachment=True,
                last_modified=self.last_modified,
            )
        except FileNotFound:
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
        Download a generic file preview.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: extension
            required: True
            type: string
            x-example: png, pdf, jpg, jpeg, ...
        responses:
            200:
                description: Generic file preview downloaded
            403:
                description: Instance not allowed
            404:
                description: Non-movie file not found
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
        Download a generic file preview as attachment.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Generic file preview downloaded as attachment
            403:
                description: Instance not allowed
            404:
                description: Standard file not found
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
            task = tasks_service.get_task(comment["object_id"])
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
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
        Download the thumbnail representing given attachment file.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: attachment_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Thumbnail downloaded
            403:
                description: Instance not allowed
            404:
                description: Picture file not found
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
        Download a thumbnail.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Thumbnail downloaded
            403:
                description: Instance not allowed
            404:
                description: Picture file not found
        """
        self.is_allowed(instance_id)

        try:
            return send_picture_file(
                self.picture_type,
                instance_id,
                last_modified=self.last_modified,
            )
        except FileNotFound:
            current_app.logger.error(
                "Picture file was not found for: %s" % instance_id
            )
            abort(404)


class PreviewFileThumbnailResource(BasePreviewPictureResource):
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


class PreviewFileThumbnailSquareResource(BasePreviewPictureResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "thumbnails-square")


class PreviewFileOriginalResource(BasePreviewPictureResource):
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
        Create a thumbnail for given object instance.
        ---
        tags:
          - Previews
        consumes:
          - multipart/form-data
          - image/png
          - application/pdf
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: True
            type: file
        responses:
            200:
                description: Thumbnail created
            404:
                description: Cannot found related object.
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
        Download the thumbnail linked to given object instance.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Thumbnail downloaded
            403:
                description: Access not allowed
            404:
                description: Object instance not found
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
            current_app.logger.error(
                "Thumbnail file was not found for: %s" % instance_id
            )
            abort(404)
        except IOError:
            current_app.logger.error(
                "Thumbnail file was not found for: %s" % instance_id
            )
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
        is_current_user = (
            persons_service.get_current_user()["id"] == instance_id
        )
        if not is_current_user and not permissions.has_admin_permissions():
            raise permissions.PermissionDenied


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
        )

    def check_allowed_to_get(self, instance_id):
        super().check_allowed_to_get(instance_id)
        user_service.check_project_access(instance_id)


class CreateProjectThumbnailResource(ProjectThumbnailResource):
    pass


class SetMainPreviewResource(Resource, ArgsMixin):
    """
    Set given preview as main preview of the related entity. This preview will
    be used to illustrate the entity.
    """

    @jwt_required()
    def put(self, preview_file_id):
        """
        Set given preview as main preview of the related entity.
        ---
        tags:
          - Previews
        description: This preview will be used to illustrate the entity.
        parameters:
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given preview set as main preview
        """
        args = self.get_args([("frame_number", None, False, int)])
        frame_number = args["frame_number"]
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        if frame_number is not None:
            if preview_file["extension"] != "mp4":
                raise ArgumentsException(
                    "Can't use a given frame on non movie preview"
                )
            preview_files_service.replace_extracted_frame_for_preview_file(
                preview_file, frame_number
            )
        asset = entities_service.update_entity_preview(
            task["entity_id"],
            preview_file_id,
        )
        assets_service.clear_asset_cache(asset["id"])
        shots_service.clear_shot_cache(asset["id"])
        return asset


class UpdatePreviewPositionResource(Resource, ArgsMixin):
    """
    Allow to change orders of previews for a single revision.
    """

    @jwt_required()
    def put(self, preview_file_id):
        """
        Allow to change orders of previews for a single revision.
        ---
        tags:
          - Previews
        description: This preview will be used to illustrate the entity.
        parameters:
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Orders of previews changed for a single revision
        """
        args = self.get_args([{"name": "position", "default": 0, "type": int}])
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_manager_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return preview_files_service.update_preview_file_position(
            preview_file_id, args["position"]
        )


class UpdateAnnotationsResource(Resource, ArgsMixin):
    """
    Allow to modify the annotations stored at the preview level.
    Modifications are applied via three fields:
    * `annotation`s to give all the annotations that need to be added.
    * `updates` that list annotations that needs to be modified.
    * `deletions` to list the IDs of annotations that needs to be removed.
    """

    @jwt_required()
    def put(self, preview_file_id):
        """
        Allow to modify the annotations stored at the preview level.
        ---
        tags:
          - Previews
        description: |
                    Modifications are applied via three fields:
                    * `annotations` to give all the annotations that need to be added.

                    * `updates` that list annotations that needs to be modified.

                    * `deletions` to list the IDs of annotations that needs to be removed.
        parameters:
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Orders of previews changed for a single revision
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
        Retrieve all preview files from open productions with states equals to processing or broken.
        ---
        tags:
          - Previews
        responses:
            200:
                description: All preview files from open productions with states equals to processing or broken
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
        Extract a frame from a preview_file
         ---
         tags:
           - Previews
         description: Extract a frame from a preview_file
         parameters:
           - in: path
             name: preview_file_id
             required: True
             type: string
             format: UUID
             x-example: a24a6ea4-ce75-4665-a070-57453082c25
         responses:
             200:
                 description: Extracted frame
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
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_manager_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
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
        Main resource to add a preview background file.
        ---
        tags:
          - Preview background file
        consumes:
          - multipart/form-data
          - image/vnd.radiance
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: file
            required: True
            type: file
        responses:
            200:
                description: Preview background file added
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
        Download a preview background file.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: extension
            required: True
            type: string
            format: extension
            x-example: hdr
        responses:
            200:
                description: Preview background file downloaded
            404:
                description: Preview background file not found
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
            current_app.logger.error(
                "Preview background file was not found for: %s" % instance_id
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
