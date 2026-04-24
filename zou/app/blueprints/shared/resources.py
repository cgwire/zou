from flask import g, request
from flask_fs.errors import FileNotFound
from flask_restful import Resource

from zou.app.blueprints.previews.resources import (
    send_movie_file,
    send_picture_file,
)
from zou.app.blueprints.shared.decorators import (
    require_valid_playlist_share_link,
)
from zou.app.services import (
    comments_service,
    files_service,
    playlist_sharing_service,
    playlists_service,
    preview_files_service,
)


class SharedPlaylistResource(Resource):
    @require_valid_playlist_share_link(with_password=True)
    def get(self, token):
        """
        Get shared playlist
        ---
        description: Retrieve a playlist with preview file revisions for a
          secret share link. No JWT; the path token (and optional query
          password) is the credential.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: query
            name: password
            required: false
            schema:
              type: string
            description: Password when the link is protected
        responses:
          200:
            description: Playlist with preview file revisions and enriched shots
            content:
              application/json:
                schema:
                  type: object
        """
        share_link = g.playlist_share_link
        playlist = playlists_service.get_playlist_with_preview_file_revisions(
            share_link["playlist_id"]
        )
        return playlist_sharing_service.enrich_shots_with_entity_info(playlist)


class SharedPlaylistGuestResource(Resource):
    @require_valid_playlist_share_link()
    def post(self, token):
        """
        Create or retrieve guest for shared playlist
        ---
        description: Create a guest identity for the shared playlist, or return
          an existing guest when `guest_id` is provided and still valid.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
        requestBody:
          required: false
          content:
            application/json:
              schema:
                type: object
                properties:
                  first_name:
                    type: string
                    default: Guest
                  last_name:
                    type: string
                  guest_id:
                    type: string
                    format: uuid
                    description: If set, return this guest if it still exists
        responses:
          200:
            description: Existing guest returned
            content:
              application/json:
                schema:
                  type: object
          201:
            description: New guest created
            content:
              application/json:
                schema:
                  type: object
        """
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
    @require_valid_playlist_share_link(with_password=True)
    def get(self, token):
        """
        List shared playlist comments
        ---
        description: List comments for tasks that appear in the shared playlist
          (aggregated from each shot's preview task). Same optional `password`
          query param as the main shared playlist when the link is protected.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: query
            name: password
            required: false
            schema:
              type: string
            description: Password when the link is protected
        responses:
          200:
            description: Comment entries for the playlist
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
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
                pass
        return comments

    @require_valid_playlist_share_link(with_password=True)
    def post(self, token):
        """
        Post comment on shared playlist
        ---
        description: Add a review comment as a guest. Requires `guest_id`,
          `task_id`, `task_status_id` and `text` when the link allows
          commenting. Optional `password` query param if the link is
          protected.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: query
            name: password
            required: false
            schema:
              type: string
            description: Password when the link is protected
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - guest_id
                  - task_id
                  - task_status_id
                properties:
                  guest_id:
                    type: string
                    format: uuid
                  task_id:
                    type: string
                    format: uuid
                  task_status_id:
                    type: string
                    format: uuid
                  text:
                    type: string
                  checklist:
                    type: array
                    items:
                      type: object
        responses:
          201:
            description: Comment created
            content:
              application/json:
                schema:
                  type: object
          400:
            description: Missing required body fields
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
          403:
            description: Comments disabled for this share link
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        share_link = g.playlist_share_link
        if not share_link.get("can_comment", True):
            return {"error": "Comments are disabled for this link"}, 403

        data = request.get_json(silent=True) or {}
        guest_id = data.get("guest_id")
        task_id = data.get("task_id")
        task_status_id = data.get("task_status_id")
        text = data.get("text", "")
        checklist = data.get("checklist") or []

        if not guest_id or not task_id or not task_status_id:
            return {"error": "Missing required fields"}, 400

        playlist_sharing_service.get_guest(guest_id)

        comment = comments_service.create_comment(
            person_id=guest_id,
            task_id=task_id,
            task_status_id=task_status_id,
            text=text,
            checklist=checklist,
            for_client=True,
        )
        return comment, 201


class SharedPlaylistAnnotationsResource(Resource):
    @require_valid_playlist_share_link()
    def post(self, token):
        """
        Save guest annotations for preview
        ---
        description: Update preview file annotations in the context of a shared
          playlist. Only allowed when the link permits commenting/annotations.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - guest_id
                  - preview_file_id
                properties:
                  guest_id:
                    type: string
                    format: uuid
                  preview_file_id:
                    type: string
                    format: uuid
                  annotations:
                    type: array
                    items:
                      type: object
        responses:
          200:
            description: Annotations stored
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    status:
                      type: string
                      example: success
          400:
            description: Missing required body fields
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
          403:
            description: Annotations disabled for this share link
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        share_link = g.playlist_share_link
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
    @require_valid_playlist_share_link()
    def get(self, token, preview_file_id):
        """
        Get shared preview file metadata
        ---
        description: Return preview file record when the request includes a
          valid share token. No JWT.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
        responses:
          200:
            description: Preview file metadata
            content:
              application/json:
                schema:
                  type: object
        """
        return files_service.get_preview_file(preview_file_id)


class SharedPlaylistPreviewFileMovieResource(Resource):
    @require_valid_playlist_share_link()
    def get(self, token, preview_file_id):
        """
        Get shared original movie preview
        ---
        description: Stream the original movie file for a preview, authorized by
          the share token. Same role as the authenticated original movie
          preview route, without JWT.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
        responses:
          200:
            description: Movie preview file stream
            content:
              video/mp4:
                schema:
                  type: string
                  format: binary
          404:
            description: Preview file not on disk
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        try:
            return send_movie_file(preview_file_id)
        except FileNotFound:
            return {"error": "Preview file not found"}, 404


class SharedPlaylistPreviewFileThumbnailResource(Resource):
    @require_valid_playlist_share_link()
    def get(self, token, preview_file_id):
        """
        Get shared preview thumbnail
        ---
        description: Serve the PNG thumbnail for a preview file when the share
          token is valid.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
        responses:
          200:
            description: Thumbnail image
            content:
              image/png:
                schema:
                  type: string
                  format: binary
          404:
            description: Thumbnail file missing
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        try:
            return send_picture_file("thumbnails", preview_file_id)
        except FileNotFound:
            return {"error": "Thumbnail not found"}, 404


class SharedPlaylistPreviewFileOriginalResource(Resource):
    @require_valid_playlist_share_link()
    def get(self, token, preview_file_id):
        """
        Get shared original picture preview
        ---
        description: Serve the full-size PNG for a still preview, authorized by
          the share token.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
        responses:
          200:
            description: Original picture file
            content:
              image/png:
                schema:
                  type: string
                  format: binary
          404:
            description: Original file missing
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        try:
            return send_picture_file("original", preview_file_id)
        except FileNotFound:
            return {"error": "Original not found"}, 404


class SharedPlaylistPreviewFileTileResource(Resource):
    @require_valid_playlist_share_link()
    def get(self, token, preview_file_id):
        """
        Get shared movie tile strip
        ---
        description: Serve the filmstrip/tile image used for timeline hover
          previews, when the share token is valid.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: path
            name: preview_file_id
            required: true
            schema:
              type: string
              format: uuid
            description: Preview file unique identifier
        responses:
          200:
            description: Tile sprite image
            content:
              image/png:
                schema:
                  type: string
                  format: binary
          404:
            description: Tile file missing
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    error:
                      type: string
        """
        try:
            return send_picture_file("tiles", preview_file_id)
        except FileNotFound:
            return {"error": "Tile not found"}, 404


class SharedPlaylistContextResource(Resource):
    @require_valid_playlist_share_link(with_password=True)
    def get(self, token):
        """
        Get shared playlist context
        ---
        description: Return minimal project and playlist context needed to
          render the shared playlist UI. Optional `password` query param when
          the link is protected.
        tags:
          - Playlists
        parameters:
          - in: path
            name: token
            required: true
            schema:
              type: string
            description: Share link token
          - in: query
            name: password
            required: false
            schema:
              type: string
            description: Password when the link is protected
        responses:
          200:
            description: Context payload for the share page
            content:
              application/json:
                schema:
                  type: object
        """
        return playlist_sharing_service.get_shared_playlist_context(token)
