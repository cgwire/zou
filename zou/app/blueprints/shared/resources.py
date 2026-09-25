from flasgger import swag_from
from flask import current_app, g, request
from flask_fs.errors import FileNotFound
from flask.views import MethodView

from zou.app.blueprints.previews.resources import (
    ALLOWED_FILE_EXTENSION,
    ALLOWED_PICTURE_EXTENSION,
    send_movie_file,
    send_preview_picture_file,
    send_preview_standard_file,
)
from zou.app.blueprints.shared.decorators import (
    require_valid_playlist_share_link,
)
from zou.app.blueprints.shared.schemas import (
    CreateGuestCommentSchema,
    CreateGuestSchema,
    EditGuestCommentSchema,
    GuestActionSchema,
    UpdateGuestAnnotationsSchema,
)
from zou.app.services import (
    comments_service,
    files_service,
    playlist_sharing_service,
    playlists_service,
    preview_files_service,
    tasks_service,
)
from zou.app.exceptions import (
    PersonNotFoundException,
    PlaylistShareLinkNotFoundException,
    PreviewFileNotFoundException,
    WrongParameterException,
)
from zou.app.utils import permissions, validation


class SharedPlaylistResource(MethodView):
    @require_valid_playlist_share_link(with_password=True)
    @swag_from("openapi/SharedPlaylistResource_get.yml")
    def get(self, token):
        """
        Get shared playlist
        """
        share_link = g.playlist_share_link
        playlist = playlists_service.get_playlist_with_preview_file_revisions(
            share_link["playlist_id"]
        )
        return playlist_sharing_service.enrich_shots_with_entity_info(playlist)


class SharedPlaylistGuestResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistGuestResource_post.yml")
    def post(self, token):
        """
        Create or retrieve guest for shared playlist
        """
        body = validation.validate_request_body(CreateGuestSchema)

        # If a guest_id is provided, try to reuse it — but only if it was
        # created from this same share link. A guest UUID leaked from
        # another link must not grant access here.
        if body.guest_id is not None:
            try:
                guest = playlist_sharing_service.get_guest_for_share_link(
                    str(body.guest_id), g.playlist_share_link
                )
                return guest
            except (
                PersonNotFoundException,
                PlaylistShareLinkNotFoundException,
            ):
                # Unknown, or created from another link: a new guest then.
                pass

        guest = playlist_sharing_service.create_guest(
            token, body.first_name, body.last_name
        )
        return guest, 201


class SharedPlaylistCommentsResource(MethodView):
    @require_valid_playlist_share_link(with_password=True)
    @swag_from("openapi/SharedPlaylistCommentsResource_get.yml")
    def get(self, token):
        """
        List shared playlist comments
        """
        share_link = g.playlist_share_link
        playlist = playlists_service.get_playlist_with_preview_file_revisions(
            share_link["playlist_id"]
        )
        task_ids = {
            shot.get("preview_file_task_id")
            for shot in playlist.get("shots", [])
            if shot.get("preview_file_task_id")
        }
        comments = []
        for task_id in task_ids:
            try:
                comments.extend(
                    playlist_sharing_service.get_shared_task_comments(task_id)
                )
            except Exception:
                current_app.logger.exception(
                    f"Failed to load shared comments for task {task_id}."
                )
        return comments

    @require_valid_playlist_share_link(with_password=True)
    @swag_from("openapi/SharedPlaylistCommentsResource_post.yml")
    def post(self, token):
        """
        Post comment on shared playlist
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        body = validation.validate_request_body(CreateGuestCommentSchema)
        guest_id = str(body.guest_id)
        task_id = str(body.task_id)
        task_status_id = str(body.task_status_id)

        try:
            playlist_sharing_service.get_guest_for_share_link(
                guest_id, g.playlist_share_link
            )
        except Exception:
            return {"error": "Guest not part of this shared playlist"}, 403

        if not _is_task_in_shared_playlist(token, task_id):
            return {"error": "Task not part of this shared playlist"}, 403

        try:
            task_status = tasks_service.get_task_status(task_status_id)
        except Exception:
            return {"error": "Task status not found"}, 400
        if not task_status.get("is_client_allowed", False):
            return {"error": "Task status not allowed for guests"}, 400

        comment = comments_service.create_comment(
            person_id=guest_id,
            task_id=task_id,
            task_status_id=task_status_id,
            text=body.text or "",
            checklist=body.checklist or [],
        )
        return comment, 201


class SharedPlaylistCommentResource(MethodView):
    """
    Edit or delete a single comment authored by a guest.
    """

    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistCommentResource_put.yml")
    def put(self, token, comment_id):
        """
        Edit guest-owned comment
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        body = validation.validate_request_body(EditGuestCommentSchema)
        # Build the trimmed dict the service expects, dropping unset
        # fields so its `if "text" in data` / `if "checklist" in data`
        # branches don't overwrite the existing value with None.
        update_data = {"guest_id": str(body.guest_id)}
        if body.text is not None:
            update_data["text"] = body.text
        if body.checklist is not None:
            update_data["checklist"] = body.checklist
        if body.task_status_id is not None:
            update_data["task_status_id"] = str(body.task_status_id)
        try:
            return playlist_sharing_service.update_guest_comment(
                comment_id, str(body.guest_id), update_data, token
            )
        except playlist_sharing_service.GuestCommentForbidden:
            return {"error": "Forbidden"}, 403
        except playlist_sharing_service.GuestCommentNotFound:
            return {"error": "Comment not found"}, 404

    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistCommentResource_delete.yml")
    def delete(self, token, comment_id):
        """
        Delete guest-owned comment
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        body = validation.validate_request_body(GuestActionSchema)
        try:
            playlist_sharing_service.delete_guest_comment(
                comment_id, str(body.guest_id), token
            )
            return "", 204
        except playlist_sharing_service.GuestCommentForbidden:
            return {"error": "Forbidden"}, 403
        except playlist_sharing_service.GuestCommentNotFound:
            return {"error": "Comment not found"}, 404


class SharedPlaylistCommentAttachmentsResource(MethodView):
    """
    Add an attachment file to a guest-owned comment.
    """

    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistCommentAttachmentsResource_post.yml")
    def post(self, token, comment_id):
        """
        Attach files to a guest-owned comment
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        guest_id = request.form.get("guest_id") or (
            request.args.get("guest_id")
        )
        try:
            comment = playlist_sharing_service.add_guest_comment_attachments(
                comment_id, guest_id, request.files, token
            )
            return comment, 201
        except playlist_sharing_service.GuestCommentForbidden:
            return {"error": "Forbidden"}, 403
        except playlist_sharing_service.GuestCommentNotFound:
            return {"error": "Comment not found"}, 404


class SharedPlaylistCommentAttachmentResource(MethodView):
    """
    Delete one attachment from a guest-owned comment.
    """

    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistCommentAttachmentResource_delete.yml")
    def delete(self, token, comment_id, attachment_file_id):
        """
        Delete an attachment from a guest-owned comment
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        body = validation.validate_request_body(GuestActionSchema)
        try:
            playlist_sharing_service.remove_guest_comment_attachment(
                comment_id, str(body.guest_id), attachment_file_id, token
            )
            return "", 204
        except playlist_sharing_service.GuestCommentForbidden:
            return {"error": "Forbidden"}, 403
        except playlist_sharing_service.GuestCommentNotFound:
            return {"error": "Comment not found"}, 404


class SharedPlaylistAttachmentFileResource(MethodView):
    """
    Download an attachment that belongs to a visible shared comment.
    """

    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistAttachmentFileResource_get.yml")
    def get(self, token, attachment_file_id, file_name):
        """
        Download attachment file
        """
        try:
            return playlist_sharing_service.download_shared_attachment(
                token, attachment_file_id, file_name
            )
        except playlist_sharing_service.GuestCommentNotFound:
            return {"error": "Attachment not found"}, 404


class SharedPlaylistAnnotationsResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistAnnotationsResource_put.yml")
    def put(self, token):
        """
        Update guest annotations for a preview file
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Annotations are disabled"}, 403

        body = validation.validate_request_body(UpdateGuestAnnotationsSchema)
        guest_id = str(body.guest_id)
        preview_file_id = str(body.preview_file_id)
        additions = body.additions or []
        updates = body.updates or []
        deletions = body.deletions or []

        try:
            playlist_sharing_service.get_guest_for_share_link(
                guest_id, share_link
            )
        except Exception:
            return {"error": "Guest not part of this shared playlist"}, 403

        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied

        preview_file = files_service.get_preview_file(preview_file_id)
        task = tasks_service.get_task(preview_file["task_id"])
        return preview_files_service.update_preview_file_annotations(
            guest_id,
            task["project_id"],
            preview_file_id,
            additions=additions,
            updates=updates,
            deletions=deletions,
        )


def _is_task_in_shared_playlist(token, task_id):
    """
    Ensure the given task id is the preview task of one of the playlist's
    shots. Used to scope guest mutations (comments, status changes) to the
    playlist exposed by the share token.
    """
    playlist = playlist_sharing_service.get_shared_playlist(token)
    tid = str(task_id)
    for shot in playlist.get("shots", []) or []:
        if str(shot.get("preview_file_task_id") or "") == tid:
            return True
    return False


class SharedPlaylistPreviewFileResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Get shared preview file metadata
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        return files_service.get_preview_file(preview_file_id)


class SharedPlaylistPreviewFileMovieResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileMovieResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Get shared original movie preview
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        try:
            return send_movie_file(preview_file_id)
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistPreviewFileThumbnailResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileThumbnailResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Get shared preview thumbnail
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        try:
            return send_preview_picture_file("thumbnails", preview_file_id)
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistPreviewFileOriginalResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileOriginalResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Get shared original picture preview
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        try:
            return send_preview_picture_file("original", preview_file_id)
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistPreviewFileExtensionResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileExtensionResource_get.yml")
    def get(self, token, preview_file_id, extension):
        """
        Get shared original picture preview for any extension
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        extension = extension.lower()
        if extension not in ALLOWED_PICTURE_EXTENSION | ALLOWED_FILE_EXTENSION:
            raise WrongParameterException(
                f"Extension not allowed: {extension}"
            )
        try:
            if extension == "png":
                return send_preview_picture_file("original", preview_file_id)
            elif extension == "pdf":
                return send_preview_standard_file(
                    preview_file_id, extension, mimetype="application/pdf"
                )
            else:
                return send_preview_standard_file(preview_file_id, extension)
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistPreviewFileTileResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileTileResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Get shared movie tile strip
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        try:
            return send_preview_picture_file("tiles", preview_file_id)
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistPreviewFileDownloadResource(MethodView):
    @require_valid_playlist_share_link()
    @swag_from("openapi/SharedPlaylistPreviewFileDownloadResource_get.yml")
    def get(self, token, preview_file_id):
        """
        Download shared preview file
        """
        if not playlist_sharing_service.is_preview_file_in_shared_playlist(
            token, preview_file_id
        ):
            raise permissions.PermissionDenied
        preview_file = files_service.get_preview_file(preview_file_id)
        extension = preview_file["extension"]
        try:
            if extension == "png":
                return send_preview_picture_file(
                    "original", preview_file_id, as_attachment=True
                )
            elif extension == "pdf":
                return send_preview_standard_file(
                    preview_file_id,
                    extension,
                    mimetype="application/pdf",
                    as_attachment=True,
                )
            elif extension == "mp4":
                return send_movie_file(preview_file_id, as_attachment=True)
            else:
                return send_preview_standard_file(
                    preview_file_id, extension, as_attachment=True
                )
        except FileNotFound:
            raise PreviewFileNotFoundException


class SharedPlaylistContextResource(MethodView):
    @require_valid_playlist_share_link(with_password=True)
    @swag_from("openapi/SharedPlaylistContextResource_get.yml")
    def get(self, token):
        """
        Get shared playlist context
        """
        return playlist_sharing_service.get_shared_playlist_context(token)
