from tests.base import ApiDBTestCase
from zou.app.models.playlist import Playlist as PlaylistModel


class PlaylistSharingTestCase(ApiDBTestCase):
    """
    One production, one asset with a task on it, and a playlist that
    positions that task. Holds no test of its own.
    """

    def share_path(self, token=None, suffix=""):
        """
        The manager side of a share link: the list, or one link, or an
        action on it.
        """
        path = f"/data/playlists/{self.playlist['id']}/share"
        if token is not None:
            path += f"/{token}"
        return path + suffix

    def shared_path(self, token, suffix=""):
        """
        The public side, the one the viewer reaches with the token.
        """
        return f"/shared/playlists/{token}{suffix}"

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_task()
        # Guest comment endpoints reject statuses that are not flagged as
        # client-allowed, so make the default status reachable from a guest.
        self.task_status.update({"is_client_allowed": True})
        self.playlist = self.generate_fixture_playlist("Test Playlist")
        # Scope guest mutations to this playlist by listing the task as one
        # of its shots.
        self.playlist_record = self.playlist  # already a serialized dict

        playlist_row = PlaylistModel.get(self.playlist["id"])
        playlist_row.update(
            {
                "shots": [
                    {
                        "id": str(self.asset.id),
                        "preview_file_task_id": str(self.task.id),
                    }
                ]
            }
        )


class BaseSharedRevisionTestCase(PlaylistSharingTestCase):
    """
    The revisions of a shot a guest reads. The shot has two positions of
    revision 1 and a revision 2 on its animation task, and a preview on
    its layout task. The playlist positions revision 1.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_shot()
        # generate_fixture_shot_task repoints self.shot_task at the task it
        # creates, so keep each one.
        self.animation_task = self.generate_fixture_shot_task()
        self.layout_task = self.generate_fixture_shot_task(
            name="Layout", task_type_id=self.task_type_layout.id
        )
        animation_task_id = self.animation_task.id
        self.pinned = self.generate_fixture_preview_file(
            task_id=animation_task_id
        )
        self.pinned_position_2 = self.generate_fixture_preview_file(
            name="main-position-2", position=2, task_id=animation_task_id
        )
        self.revision_2 = self.generate_fixture_preview_file(
            revision=2, task_id=animation_task_id
        )
        self.layout_preview = self.generate_fixture_preview_file(
            task_id=self.layout_task.id
        )
        self.pinned_annotations = [
            {"time": 0, "drawing": {"objects": [{"id": "pinned-stroke"}]}}
        ]
        self.pinned.update({"annotations": self.pinned_annotations})
        self.revision_2.update(
            {
                "annotations": [
                    {
                        "time": 0,
                        "drawing": {"objects": [{"id": "hidden-stroke"}]},
                    }
                ]
            }
        )
        self.pin(self.entry(self.pinned))

    def entry(self, preview=None):
        """
        A playlist entry of the shot in the builder format, positioned on
        given preview, or on none.
        """
        entry = {"entity_id": str(self.shot.id)}
        if preview is not None:
            entry["preview_file_id"] = str(preview.id)
        return entry

    def pin(self, *entries):
        PlaylistModel.get(self.playlist["id"]).update({"shots": list(entries)})

    def guest_get(self, suffix=""):
        """
        Read the shared playlist, or one of its routes, the way a viewer
        does: through a fresh link and with no token at all.
        """
        link = self.post(self.share_path(), {}, 201)
        response = self.app.get(self.shared_path(link["token"], suffix))
        self.assertEqual(response.status_code, 200)
        return response.json
