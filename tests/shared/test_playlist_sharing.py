from tests.base import ApiDBTestCase


class PlaylistSharingTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        # Guest comment endpoints reject statuses that are not flagged as
        # client-allowed, so make the default status reachable from a guest.
        self.task_status.update({"is_client_allowed": True})
        self.playlist = self.generate_fixture_playlist("Test Playlist")
        # Scope guest mutations to this playlist by listing the task as one
        # of its shots.
        self.playlist_record = self.playlist  # already a serialized dict
        from zou.app.models.playlist import Playlist as PlaylistModel

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

    # --- Authenticated share link management (manager+) ---

    def test_create_share_link(self):
        result = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        self.assertIsNotNone(result["token"])
        self.assertTrue(result["is_active"])
        self.assertTrue(result["can_comment"])

    def test_list_share_links(self):
        self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        result = self.get(f"/data/playlists/{self.playlist['id']}/share")
        self.assertEqual(len(result), 1)

    def test_revoke_share_link(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.delete(
            f"/data/playlists/{self.playlist['id']}/share/{link['token']}",
            200,
        )
        result = self.get(f"/data/playlists/{self.playlist['id']}/share")
        self.assertEqual(len(result), 0)

    # --- Public shared playlist routes ---

    def test_get_shared_playlist(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        result = self.get(f"/shared/playlists/{link['token']}")
        self.assertEqual(result["id"], self.playlist["id"])

    def test_get_shared_playlist_invalid_token(self):
        self.log_out()
        self.get("/shared/playlists/invalid-token", 404)

    def test_get_shared_playlist_revoked(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.delete(
            f"/data/playlists/{self.playlist['id']}/share/{link['token']}",
            200,
        )
        self.log_out()
        self.get(f"/shared/playlists/{link['token']}", 404)

    def test_get_shared_playlist_context(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        result = self.get(f"/shared/playlists/{link['token']}/context")
        self.assertIn("project", result)
        self.assertIn("task_types", result)
        self.assertIn("task_statuses", result)

    # --- Guest management ---

    def test_create_guest(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "John", "last_name": "Doe"},
            201,
        )
        self.assertEqual(guest["first_name"], "John")
        self.assertTrue(guest["is_guest"])

    def test_reuse_guest(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "John"},
            201,
        )
        guest2 = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "Jane", "guest_id": guest["id"]},
            200,
        )
        self.assertEqual(guest["id"], guest2["id"])

    # --- Guest comments ---

    def test_guest_comment(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "Reviewer"},
            201,
        )
        comment = self.post(
            f"/shared/playlists/{link['token']}/comments",
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "Great work!",
            },
            201,
        )
        self.assertEqual(comment["text"], "Great work!")

    def test_guest_comment_rejects_foreign_task(self):
        """A guest cannot post a comment on a task that is not part of the
        playlist they hold a share link to."""
        from zou.app.models.task import Task

        foreign_task = Task.create(
            name="Foreign",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
        )
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            f"/shared/playlists/{link['token']}/comments",
            {
                "guest_id": guest["id"],
                "task_id": str(foreign_task.id),
                "task_status_id": str(self.task_status.id),
                "text": "should be rejected",
            },
            403,
        )

    def test_guest_comment_rejects_non_client_status(self):
        """A guest cannot set a task status that is not client-allowed."""
        from zou.app.models.task_status import TaskStatus

        manager_status = TaskStatus.create(
            name="Approved",
            short_name="apr",
            color="#000000",
            is_client_allowed=False,
        )
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            f"/shared/playlists/{link['token']}/comments",
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(manager_status.id),
                "text": "should be rejected",
            },
            400,
        )

    def test_guest_comment_disabled(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": False},
            201,
        )
        self.log_out()
        guest = self.post(
            f"/shared/playlists/{link['token']}/guest",
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            f"/shared/playlists/{link['token']}/comments",
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "Should fail",
            },
            403,
        )
