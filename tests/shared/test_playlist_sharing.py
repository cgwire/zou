from tests.base import ApiDBTestCase

from zou.app.services import (
    playlist_sharing_service,
    playlists_service,
)


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
        self.playlist = playlists_service.create_playlist(
            self.project.id,
            "Test Playlist",
            self.user["id"],
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
        result = self.get(
            f"/data/playlists/{self.playlist['id']}/share"
        )
        self.assertEqual(len(result), 1)

    def test_revoke_share_link(self):
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.delete(
            f"/data/playlists/{self.playlist['id']}/share/{link['token']}"
        )
        result = self.get(
            f"/data/playlists/{self.playlist['id']}/share"
        )
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
            f"/data/playlists/{self.playlist['id']}/share/{link['token']}"
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
        result = self.get(
            f"/shared/playlists/{link['token']}/context"
        )
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
