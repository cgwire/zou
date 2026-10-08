from zou.app.models.build_job import BuildJob
from zou.app.models.notification import Notification
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.utils import events
from zou.app.services import (
    playlist_builds_service,
    playlists_service,
)


def remove_playlist_dependents(playlist_dict):
    """
    Delete what hangs off given playlist: its notifications, its build jobs
    (with their movie files) and its share links. The one cascade both the
    service and the CRUD route run, so a dependent added here is gone from
    both.
    """
    playlist_id = playlist_dict["id"]
    notifications = Notification.query.filter_by(playlist_id=playlist_id).all()
    for notification in notifications:
        notification.delete()
    jobs = BuildJob.query.filter_by(playlist_id=playlist_id).all()
    for job in jobs:
        playlist_builds_service.remove_build_job_impl(
            playlist_dict, job.serialize()
        )
    share_links = PlaylistShareLink.query.filter_by(
        playlist_id=playlist_id
    ).all()
    for share_link in share_links:
        share_link.delete()


def remove_playlist(playlist_id):
    """
    Remove given playlist from database (and delete related build jobs).
    """
    playlist = playlists_service.get_playlist_raw(playlist_id)
    playlist_dict = playlist.serialize()
    remove_playlist_dependents(playlist_dict)
    playlist.delete()
    events.emit(
        "playlist:delete",
        {"playlist_id": playlist_dict["id"]},
        project_id=playlist_dict["project_id"],
    )
    return playlist_dict
