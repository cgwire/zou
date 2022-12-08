import os

from flask import abort, request, current_app
from flask import send_file as flask_send_file
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required
from flask_fs.errors import FileNotFound

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.stores import file_store
from zou.app.services import (
    assets_service,
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
)
from zou.app.services.exception import PreviewFileNotFoundException


ALLOWED_PICTURE_EXTENSION = [".png", ".jpg", ".jpeg", ".jpe"]
ALLOWED_MOVIE_EXTENSION = [
    ".avi",
    ".mp4",
    ".m4v",
    ".mkv",
    ".mov",
    ".webm",
    ".wmv",
]
ALLOWED_FILE_EXTENSION = [
    ".ae",
    ".ai",
    ".blend",
    ".comp",
    ".exr",
    ".fbx",
    ".fla",
    ".flv",
    ".gif",
    ".hip",
    ".ma",
    ".mb",
    ".obj",
    ".pdf",
    ".psd",
    ".rar",
    ".sbbkp",
    ".svg",
    ".swf",
    ".zip",
    ".mp3",
    ".wav",
    ".glb",
    ".gltf",
]


def send_standard_file(
    preview_file_id,
    extension,
    mimetype="application/octet-stream",
    as_attachment=False,
):
    return send_storage_file(
        file_store.get_local_file_path,
        file_store.open_file,
        "previews",
        preview_file_id,
        extension,
        mimetype=mimetype,
        as_attachment=as_attachment,
    )


def send_movie_file(preview_file_id, as_attachment=False, lowdef=False):
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
    )


def send_picture_file(prefix, preview_file_id, as_attachment=False):
    return send_storage_file(
        file_store.get_local_picture_path,
        file_store.open_picture,
        prefix,
        preview_file_id,
        "png",
        mimetype="image/png",
        as_attachment=as_attachment,
    )


def send_storage_file(
    get_local_path,
    open_file,
    prefix,
    preview_file_id,
    extension,
    mimetype="application/octet-stream",
    as_attachment=False,
):
    """
    Send file from storage. If it's not a local storage, cache the file in
    a temporary folder before sending it. It accepts conditional headers.
    """
    file_size = None
    try:
        if prefix in ["movies", "pictures", "previews", "originals"]:
            preview_file = files_service.get_preview_file(preview_file_id)
            preview_file["file_size"]
    except PreviewFileNotFoundException:
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

    attachment_filename = ""
    if as_attachment:
        attachment_filename = names_service.get_preview_file_name(
            preview_file_id
        )

    try:
        return flask_send_file(
            file_path,
            conditional=True,
            mimetype=mimetype,
            as_attachment=as_attachment,
            attachment_filename=attachment_filename,
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

    @jwt_required
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
        extension = ".%s" % file_name_parts.pop().lower()
        original_file_name = ".".join(file_name_parts)

        if extension in ALLOWED_PICTURE_EXTENSION:
            self.save_picture_preview(instance_id, uploaded_file)
            preview_file = preview_files_service.update_preview_file(
                instance_id,
                {
                    "extension": "png",
                    "original_name": original_file_name,
                    "status": "ready",
                },
            )
            self.emit_app_preview_event(instance_id)
            return preview_file, 201

        elif extension in ALLOWED_MOVIE_EXTENSION:
            try:
                normalize = True
                if "normalize" in request.args:
                    normalize = self.get_bool_parameter("normalize")
                self.save_movie_preview(instance_id, uploaded_file, normalize)
            except Exception as e:
                current_app.logger.error(e, exc_info=1)
                current_app.logger.error("Normalization failed.")
                deletion_service.remove_preview_file_by_id(instance_id)
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
                    "extension": extension[1:],
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
        tmp_folder = current_app.config["TMP_DIR"]
        original_tmp_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        file_size = fs.get_file_size(original_tmp_path)
        preview_files_service.update_preview_file(
            instance_id, {"file_size": file_size}, silent=True
        )
        return preview_files_service.save_variants(
            instance_id, original_tmp_path
        )

    def save_movie_preview(
        self, preview_file_id, uploaded_file, normalize=True
    ):
        """
        Get uploaded movie, normalize it then build thumbnails then save
        everything in the file storage.
        """
        no_job = self.get_no_job()
        tmp_folder = current_app.config["TMP_DIR"]
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
        tmp_folder = current_app.config["TMP_DIR"]
        file_name = instance_id + extension
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


class PreviewFileMovieResource(Resource):
    """
    Allow to download a movie preview.
    """

    def __init__(self):
        Resource.__init__(self)

    def is_exist(self, preview_file_id):
        return files_service.get_preview_file(preview_file_id) is not None

    def is_allowed(self, preview_file_id):
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        try:
            user_service.check_project_access(task["project_id"])
            user_service.check_entity_access(task["entity_id"])
            return True
        except permissions.PermissionDenied:
            return False

    @jwt_required
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
        if not self.is_exist(instance_id):
            abort(404)

        if not self.is_allowed(instance_id):
            abort(403)

        try:
            return send_movie_file(instance_id)
        except FileNotFound:
            current_app.logger.error(
                "Movie file was not found for: %s" % instance_id
            )
            abort(404)


class PreviewFileLowMovieResource(PreviewFileMovieResource):
    """
    Allow to download a lowdef movie preview.
    """

    @jwt_required
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
        if not self.is_allowed(instance_id):
            abort(403)

        try:
            return send_movie_file(instance_id, lowdef=True)
        except Exception as e:
            try:
                return send_movie_file(instance_id)
            except FileNotFound:
                current_app.logger.error(
                    "Movie file was not found for: %s" % instance_id
                )
                abort(404)


class PreviewFileMovieDownloadResource(PreviewFileMovieResource):
    """
    Allow to download a movie preview.
    """

    @jwt_required
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
        if not self.is_allowed(instance_id):
            abort(403)

        try:
            return send_movie_file(instance_id, as_attachment=True)
        except FileNotFound:
            current_app.logger.error(
                "Movie file was not found for: %s" % instance_id
            )
            abort(404)


class PreviewFileResource(Resource):
    """
    Allow to download a generic file preview.
    """

    def __init__(self):
        Resource.__init__(self)

    def is_exist(self, preview_file_id):
        return files_service.get_preview_file(preview_file_id) is not None

    def is_allowed(self, preview_file_id):
        if permissions.has_manager_permissions():
            return True
        else:
            preview_file = files_service.get_preview_file(preview_file_id)
            task = tasks_service.get_task(preview_file["task_id"])
            try:
                user_service.check_project_access(task["project_id"])
                user_service.check_entity_access(task["entity_id"])
                return True
            except permissions.PermissionDenied:
                return False

    @jwt_required
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
        if not self.is_exist(instance_id):
            abort(404)

        if not self.is_allowed(instance_id):
            abort(403)

        try:
            if extension == "png":
                return send_picture_file("original", instance_id)
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_standard_file(instance_id, extension, mimetype)
            else:
                return send_standard_file(instance_id, extension)

        except FileNotFound:
            current_app.logger.error(
                "Non-movie file was not found for: %s" % instance_id
            )
            abort(404)


class PreviewFileDownloadResource(PreviewFileResource):
    """
    Allow to download a generic file preview as attachment.
    """

    def __init__(self):
        PreviewFileResource.__init__(self)

    @jwt_required
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
        if not self.is_allowed(instance_id):
            abort(403)

        preview_file = files_service.get_preview_file(instance_id)
        extension = preview_file["extension"]

        try:
            if extension == "png":
                return send_picture_file(
                    "original", instance_id, as_attachment=True
                )
            elif extension == "pdf":
                mimetype = "application/pdf"
                return send_standard_file(
                    instance_id, extension, mimetype, as_attachment=True
                )
            else:
                return send_standard_file(
                    instance_id, extension, as_attachment=True
                )
        except FileNotFound:
            current_app.logger.error(
                "Standard file was not found for: %s" % instance_id
            )
            abort(404)


class BasePreviewPictureResource(Resource):
    """
    Base class to download a thumbnail.
    """

    def __init__(self, picture_type):
        Resource.__init__(self)
        self.picture_type = picture_type

    def is_exist(self, preview_file_id):
        return files_service.get_preview_file(preview_file_id) is not None

    def is_allowed(self, preview_file_id):
        if permissions.has_manager_permissions():
            return True
        else:
            preview_file = files_service.get_preview_file(preview_file_id)
            task = tasks_service.get_task(preview_file["task_id"])
            try:
                user_service.check_project_access(task["project_id"])
                user_service.check_entity_access(task["entity_id"])
                return True
            except permissions.PermissionDenied:
                return False

    @jwt_required
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
        if not self.is_exist(instance_id):
            abort(404)

        if not self.is_allowed(instance_id):
            abort(403)

        try:
            return send_picture_file(self.picture_type, instance_id)
        except FileNotFound:
            current_app.logger.error(
                "Picture file was not found for: %s" % instance_id
            )
            abort(404)


class PreviewFileThumbnailResource(BasePreviewPictureResource):
    def __init__(self):
        BasePreviewPictureResource.__init__(self, "thumbnails")


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


class BaseCreatePictureResource(Resource):
    """
    Base class to create a thumbnail.
    """

    def __init__(self, data_type, size=thumbnail_utils.RECTANGLE_SIZE):
        Resource.__init__(self)
        self.data_type = data_type
        self.size = size

    def check_permissions(self, instance_id):
        permissions.check_admin_permissions()

    def prepare_creation(self, instance_id):
        pass

    def clear_cache_file(self, preview_file_id):
        if config.FS_BACKEND != "local":
            file_path = os.path.join(
                config.TMP_DIR,
                "cache-%s-%s.%s" % ("thumbnails", preview_file_id, "png"),
            )
            if os.path.exists(file_path):
                os.remove(file_path)
        return preview_file_id

    def emit_event(self, instance_id):
        model_name = self.data_type[:-1]
        events.emit(
            "%s:set-thumbnail" % model_name,
            {"%s_id" % model_name: instance_id},
        )

    @jwt_required
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
        if not self.is_exist(instance_id):
            abort(404)

        self.check_permissions(instance_id)
        self.prepare_creation(instance_id)

        tmp_folder = current_app.config["TMP_DIR"]
        uploaded_file = request.files["file"]
        thumbnail_path = thumbnail_utils.save_file(
            tmp_folder, instance_id, uploaded_file
        )
        thumbnail_path = thumbnail_utils.turn_into_thumbnail(
            thumbnail_path, size=self.size
        )
        file_store.add_picture("thumbnails", instance_id, thumbnail_path)
        os.remove(thumbnail_path)
        self.clear_cache_file(instance_id)

        thumbnail_url_path = thumbnail_utils.url_path(
            self.data_type, instance_id
        )
        self.emit_event(instance_id)
        return {"thumbnail_path": thumbnail_url_path}, 201


class BasePictureResource(Resource):
    """
    Base resource to download a thumbnail.
    """

    def __init__(self, subfolder):
        Resource.__init__(self)
        self.subfolder = subfolder

    def is_allowed(self, instance_id):
        return True

    @jwt_required
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
        if not self.is_exist(instance_id):
            abort(404)

        if not self.is_allowed(instance_id):
            abort(403)

        try:
            return send_picture_file("thumbnails", instance_id)
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


class CreatePersonThumbnailResource(BaseCreatePictureResource):
    def __init__(self):
        BaseCreatePictureResource.__init__(
            self, "persons", thumbnail_utils.BIG_SQUARE_SIZE
        )

    def is_exist(self, person_id):
        return persons_service.get_person(person_id) is not None

    def check_permissions(self, instance_id):
        is_current_user = (
            persons_service.get_current_user()["id"] != instance_id
        )
        if is_current_user and not permissions.has_manager_permissions():
            raise permissions.PermissionDenied

    def prepare_creation(self, instance_id):
        return persons_service.update_person(instance_id, {"has_avatar": True})


class PersonThumbnailResource(BasePictureResource):
    def __init__(self):
        BasePictureResource.__init__(self, "persons")

    def is_exist(self, person_id):
        return persons_service.get_person(person_id) is not None


class CreateOrganisationThumbnailResource(BaseCreatePictureResource):
    def __init__(self):
        BaseCreatePictureResource.__init__(
            self, "organisations", thumbnail_utils.BIG_SQUARE_SIZE
        )

    def is_exist(self, organisation_id):
        return True

    def check_permissions(self, organisation_id):
        if not permissions.has_admin_permissions():
            raise permissions.PermissionDenied

    def prepare_creation(self, organisation_id):
        return persons_service.update_organisation(
            organisation_id, {"has_avatar": True}
        )


class OrganisationThumbnailResource(BasePictureResource):
    def __init__(self):
        BasePictureResource.__init__(self, "organisations")

    def is_exist(self, organisation_id):
        return True


class CreateProjectThumbnailResource(BaseCreatePictureResource):
    def __init__(self):
        BaseCreatePictureResource.__init__(
            self, "projects", thumbnail_utils.SQUARE_SIZE
        )

    def is_exist(self, project_id):
        return projects_service.get_project(project_id) is not None

    def prepare_creation(self, instance_id):
        return projects_service.update_project(
            instance_id, {"has_avatar": True}
        )


class ProjectThumbnailResource(BasePictureResource):
    def __init__(self):
        BasePictureResource.__init__(self, "projects")

    def is_exist(self, project_id):
        return projects_service.get_project(project_id) is not None

    def is_allowed(self, project_id):
        try:
            user_service.check_project_access(project_id)
            return True
        except permissions.PermissionDenied:
            return False


class LegacySetMainPreviewResource(Resource):
    @jwt_required
    def put(self, entity_id, preview_file_id):
        """
        Set main preview to given file.
        ---
        tags:
          - Previews
        parameters:
          - in: path
            name: entity_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: preview_file_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Main preview set
        """
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        return entities_service.update_entity_preview(
            entity_id, preview_file_id
        )


class SetMainPreviewResource(Resource):
    """
    Set given preview as main preview of the related entity. This preview will
    be used to illustrate the entity.
    """

    @jwt_required
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
        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        asset = entities_service.update_entity_preview(
            task["entity_id"], preview_file_id
        )
        assets_service.clear_asset_cache(asset["id"])
        shots_service.clear_shot_cache(asset["id"])
        return asset


class UpdatePreviewPositionResource(Resource, ArgsMixin):
    """
    Allow to change orders of previews for a single revision.
    """

    @jwt_required
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
        parser = reqparse.RequestParser()
        parser.add_argument("position", default=0, type=int)
        args = parser.parse_args()
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

    @jwt_required
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

    @jwt_required
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
