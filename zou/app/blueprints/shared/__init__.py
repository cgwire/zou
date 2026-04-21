from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from zou.app.blueprints.shared.resources import (
    SharedPlaylistResource,
    SharedPlaylistGuestResource,
    SharedPlaylistCommentsResource,
    SharedPlaylistAnnotationsResource,
    SharedPlaylistPreviewFileResource,
    SharedPlaylistPreviewFileMovieResource,
    SharedPlaylistPreviewFileThumbnailResource,
    SharedPlaylistPreviewFileOriginalResource,
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
        "/shared/playlists/<token>/context",
        SharedPlaylistContextResource,
    ),
]

blueprint = Blueprint("shared", "shared")
api = configure_api_from_blueprint(blueprint, routes)
