from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.shared.resources import (
    SharedPlaylistResource,
    SharedPlaylistGuestResource,
    SharedPlaylistCommentsResource,
    SharedPlaylistCommentResource,
    SharedPlaylistCommentAttachmentsResource,
    SharedPlaylistCommentAttachmentResource,
    SharedPlaylistAttachmentFileResource,
    SharedPlaylistAnnotationsResource,
    SharedPlaylistPreviewFileResource,
    SharedPlaylistPreviewFileMovieResource,
    SharedPlaylistPreviewFileThumbnailResource,
    SharedPlaylistPreviewFileOriginalResource,
    SharedPlaylistPreviewFileTileResource,
    SharedPlaylistContextResource,
)

routes = [
    (
        "/shared/playlists/<token>",
        SharedPlaylistResource,
    ),
    (
        "/shared/playlists/<token>/guest",
        SharedPlaylistGuestResource,
    ),
    (
        "/shared/playlists/<token>/comments",
        SharedPlaylistCommentsResource,
    ),
    (
        "/shared/playlists/<token>/comments/<comment_id>",
        SharedPlaylistCommentResource,
    ),
    (
        "/shared/playlists/<token>/comments/<comment_id>/attachments",
        SharedPlaylistCommentAttachmentsResource,
    ),
    (
        "/shared/playlists/<token>/comments/<comment_id>/"
        "attachments/<attachment_id>",
        SharedPlaylistCommentAttachmentResource,
    ),
    (
        "/shared/playlists/<token>/attachment-files/"
        "<attachment_id>/file/<file_name>",
        SharedPlaylistAttachmentFileResource,
    ),
    (
        "/shared/playlists/<token>/annotations",
        SharedPlaylistAnnotationsResource,
    ),
    (
        "/shared/playlists/<token>/preview-files/<preview_file_id>",
        SharedPlaylistPreviewFileResource,
    ),
    (
        "/shared/playlists/<token>/movies/originals/"
        "preview-files/<preview_file_id>.mp4",
        SharedPlaylistPreviewFileMovieResource,
    ),
    (
        "/shared/playlists/<token>/pictures/thumbnails/"
        "preview-files/<preview_file_id>.png",
        SharedPlaylistPreviewFileThumbnailResource,
    ),
    (
        "/shared/playlists/<token>/pictures/originals/"
        "preview-files/<preview_file_id>.png",
        SharedPlaylistPreviewFileOriginalResource,
    ),
    (
        "/shared/playlists/<token>/movies/tiles/"
        "preview-files/<preview_file_id>.png",
        SharedPlaylistPreviewFileTileResource,
    ),
    (
        "/shared/playlists/<token>/context",
        SharedPlaylistContextResource,
    ),
]

blueprint = Blueprint("shared", "shared")
api = configure_api_from_blueprint(blueprint, routes)
