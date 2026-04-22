from flask import request
from flask_restful import Resource

from zou.app.blueprints.previews.resources import (
    send_movie_file,
    send_picture_file,
)
from zou.app.services import (
    comments_service,
    files_service,
    playlist_sharing_service,
    playlists_service,
    preview_files_service,
    tasks_service,
)


class SharedPlaylistResource(Resource):
    """
    GET /api/shared/playlists/<token>
    Return playlist data with preview file revisions, accessible via
    a share token. No authentication required — token is the credential.
    """

    def get(self, token):
        password = request.args.get("password")
        share_link = playlist_sharing_service.validate_share_token(
            token, password=password
        )
        playlist = (
            playlists_service.get_playlist_with_preview_file_revisions(
                share_link["playlist_id"]
            )
        )
        return playlist_sharing_service.enrich_shots_with_entity_info(
            playlist
        )


class SharedPlaylistGuestResource(Resource):
    """
    POST /api/shared/playlists/<token>/guest
    Create or retrieve a guest identity for the shared playlist.
    Body: { "first_name": "John", "last_name": "Doe" (optional) }
    """

    def post(self, token):
        playlist_sharing_service.validate_share_token(token)
        data = request.get_json(silent=True) or {}
        first_name = data.get("first_name", "Guest")
        last_name = data.get("last_name", "")

        # If a guest_id is provided, try to reuse it
        guest_id = data.get("guest_id")
        if guest_id:
            try:
                guest = playlist_sharing_service.get_guest(guest_id)
                return guest
            except Exception:
                pass

        guest = playlist_sharing_service.create_guest(
            token, first_name, last_name
        )
        return guest, 201


class SharedPlaylistCommentsResource(Resource):
    """
    GET /api/shared/playlists/<token>/comments
    List comments for the playlist's tasks.

    POST /api/shared/playlists/<token>/comments
    Post a comment as a guest.
    Body: { "guest_id": "...", "task_id": "...",
            "task_status_id": "...", "text": "..." }
    """

    def get(self, token):
        share_link = playlist_sharing_service.validate_share_token(
            token
        )
        playlist = playlist_sharing_service.get_shared_playlist(token)
        comments = []
        for shot_entry in playlist.get("shots", []):
            entity_id = shot_entry.get("entity_id")
            if entity_id:
                task_id = shot_entry.get("preview_file_task_id")
                if task_id:
                    try:
                        task_comments = tasks_service.get_comments(
                            task_id, is_client=True
                        )
                        comments.extend(task_comments)
                    except Exception:
                        pass
        return comments

    def post(self, token):
        share_link = playlist_sharing_service.validate_share_token(
            token
        )
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        data = request.get_json(silent=True) or {}
        guest_id = data.get("guest_id")
        task_id = data.get("task_id")
        task_status_id = data.get("task_status_id")
        text = data.get("text", "")

        if not guest_id or not task_id or not task_status_id:
            return {"error": "Missing required fields"}, 400

        playlist_sharing_service.get_guest(guest_id)

        comment = comments_service.create_comment(
            person_id=guest_id,
            task_id=task_id,
            task_status_id=task_status_id,
            text=text,
            for_client=True,
        )
        return comment, 201


class SharedPlaylistAnnotationsResource(Resource):
    """
    POST /api/shared/playlists/<token>/annotations
    Save an annotation as a guest.
    Body: { "guest_id": "...", "preview_file_id": "...",
            "annotations": [...] }
    """

    def post(self, token):
        share_link = playlist_sharing_service.validate_share_token(
            token
        )
        if not share_link.get("can_comment", True):
            return {"error": "Annotations are disabled"}, 403

        data = request.get_json(silent=True) or {}
        guest_id = data.get("guest_id")
        preview_file_id = data.get("preview_file_id")
        annotations = data.get("annotations", [])

        if not guest_id or not preview_file_id:
            return {"error": "Missing required fields"}, 400

        playlist_sharing_service.get_guest(guest_id)

        files_service.get_preview_file(preview_file_id)
        preview_files_service.update_preview_file(
            preview_file_id, {"annotations": annotations}
        )
        return {"status": "success"}


class SharedPlaylistPreviewFileResource(Resource):
    """
    GET /api/shared/playlists/<token>/preview-files/<preview_file_id>
    Return preview file metadata accessible via the share token.
    """

    def get(self, token, preview_file_id):
        playlist_sharing_service.validate_share_token(token)
        return files_service.get_preview_file(preview_file_id)


class SharedPlaylistPreviewFileMovieResource(Resource):
    """
    GET /api/shared/playlists/<token>/movies/originals/
        preview-files/<preview_file_id>.mp4
    Stream an original movie preview file.
    """

    def get(self, token, preview_file_id):
        playlist_sharing_service.validate_share_token(token)
        return send_movie_file(preview_file_id)


class SharedPlaylistPreviewFileThumbnailResource(Resource):
    """
    GET /api/shared/playlists/<token>/pictures/thumbnails/
        preview-files/<preview_file_id>.png
    Serve a preview file thumbnail.
    """

    def get(self, token, preview_file_id):
        playlist_sharing_service.validate_share_token(token)
        return send_picture_file("thumbnails", preview_file_id)


class SharedPlaylistPreviewFileOriginalResource(Resource):
    """
    GET /api/shared/playlists/<token>/pictures/originals/
        preview-files/<preview_file_id>.png
    Serve an original preview picture.
    """

    def get(self, token, preview_file_id):
        playlist_sharing_service.validate_share_token(token)
        return send_picture_file("original", preview_file_id)


class SharedPlaylistContextResource(Resource):
    """
    GET /api/shared/playlists/<token>/context
    Return minimal project context for displaying the shared playlist.
    """

    def get(self, token):
        password = request.args.get("password")
        playlist_sharing_service.validate_share_token(
            token, password=password
        )
        return playlist_sharing_service.get_shared_playlist_context(
            token
        )
