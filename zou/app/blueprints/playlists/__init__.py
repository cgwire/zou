from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    BuildJobResource,
    BuildPlaylistMovieResource,
    EntityPreviewsResource,
    EpisodePlaylistsResource,
    ProjectPlaylistsResource,
    ProjectAllPlaylistsResource,
    ProjectBuildJobsResource,
    ProjectPlaylistResource,
    PlaylistDownloadResource,
    PlaylistZipDownloadResource,
    TempPlaylistResource
)


routes = [
    ("/data/projects/<project_id>/playlists", ProjectPlaylistsResource),
    ("/data/projects/<project_id>/playlists/all", ProjectAllPlaylistsResource),
    (
        "/data/projects/<project_id>/episodes/<episode_id>/playlists",
        EpisodePlaylistsResource,
    ),
    (
        "/data/projects/<project_id>/playlists/<playlist_id>",
        ProjectPlaylistResource,
    ),
    (
        "/data/playlists/entities/<entity_id>/preview-files",
        EntityPreviewsResource,
    ),
    ("/data/playlists/<playlist_id>/jobs/<build_job_id>", BuildJobResource),
    ("/data/projects/<project_id>/build-jobs", ProjectBuildJobsResource),
    ("/data/playlists/<playlist_id>/build/mp4", BuildPlaylistMovieResource),
    (
        "/data/playlists/<playlist_id>/jobs/<build_job_id>/build/mp4",
        PlaylistDownloadResource,
    ),
    ("/data/playlists/<playlist_id>/download/zip", PlaylistZipDownloadResource),
    ("/data/projects/<project_id>/playlists/temp", TempPlaylistResource),
]

blueprint = Blueprint("playlists", "playlists")
api = configure_api_from_blueprint(blueprint, routes)
