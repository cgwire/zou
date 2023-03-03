from zou.app.utils.api import create_blueprint_for_api

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
    TempPlaylistResource,
)


routes = [
    ("/data/projects/<uuid:project_id>/playlists", ProjectPlaylistsResource),
    (
        "/data/projects/<uuid:project_id>/playlists/all",
        ProjectAllPlaylistsResource,
    ),
    (
        "/data/projects/<uuid:project_id>/episodes/<uuid:episode_id>/playlists",
        EpisodePlaylistsResource,
    ),
    (
        "/data/projects/<uuid:project_id>/playlists/<uuid:playlist_id>",
        ProjectPlaylistResource,
    ),
    (
        "/data/playlists/entities/<uuid:entity_id>/preview-files",
        EntityPreviewsResource,
    ),
    (
        "/data/playlists/<uuid:playlist_id>/jobs/<uuid:build_job_id>",
        BuildJobResource,
    ),
    ("/data/projects/<uuid:project_id>/build-jobs", ProjectBuildJobsResource),
    (
        "/data/playlists/<uuid:playlist_id>/build/mp4",
        BuildPlaylistMovieResource,
    ),
    (
        "/data/playlists/<uuid:playlist_id>/jobs/<uuid:build_job_id>/build/mp4",
        PlaylistDownloadResource,
    ),
    (
        "/data/playlists/<uuid:playlist_id>/download/zip",
        PlaylistZipDownloadResource,
    ),
    ("/data/projects/<uuid:project_id>/playlists/temp", TempPlaylistResource),
]

blueprint = create_blueprint_for_api("playlists", routes)
