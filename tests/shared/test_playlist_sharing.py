from tests.base import ApiDBTestCase

from zou.app.utils import events


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

    def test_share_link_routes_check_project_access(self):
        """A manager who is not on the playlist's project must not be
        able to list, create, or revoke share links for that playlist
        (cross-project IDOR)."""
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )

        self.generate_fixture_user_manager()
        self.log_out()
        self.log_in_manager()

        self.get(f"/data/playlists/{self.playlist['id']}/share", 403)
        self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            403,
        )
        self.delete(
            f"/data/playlists/{self.playlist['id']}/share/{link['token']}",
            403,
        )

    def test_revoke_share_link_rejects_mismatched_playlist(self):
        """A token must only be revocable through the URL of the playlist
        it actually belongs to. Otherwise an admin/manager who knows any
        token could revoke it via any playlist URL they have access to."""
        from zou.app.models.playlist import Playlist

        other_playlist = Playlist.create(
            name="Other Playlist",
            project_id=self.project.id,
            for_entity="shot",
            shots=[],
        ).serialize()

        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.delete(
            f"/data/playlists/{other_playlist['id']}/share/{link['token']}",
            404,
        )

    def test_share_link_password_is_hashed_and_not_serialized(self):
        """Manager-facing endpoints must never return the share link
        password, and the value stored at rest must be a bcrypt hash, not
        plaintext."""
        from zou.app.models.playlist_share_link import PlaylistShareLink

        plaintext = "topsecret123"
        result = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"password": plaintext},
            201,
        )
        self.assertNotIn("password", result)
        self.assertTrue(result.get("has_password"))

        listing = self.get(f"/data/playlists/{self.playlist['id']}/share")
        self.assertEqual(len(listing), 1)
        self.assertNotIn("password", listing[0])
        self.assertTrue(listing[0].get("has_password"))

        stored = PlaylistShareLink.get_by(token=result["token"])
        self.assertIsNotNone(stored.password)
        self.assertNotEqual(stored.password, plaintext)
        self.assertTrue(stored.password.startswith("$2"))

    def test_share_link_password_validates_with_bcrypt(self):
        """The shared playlist endpoint must accept the correct password
        (verified against the bcrypt hash) and reject incorrect ones."""
        plaintext = "topsecret123"
        result = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"password": plaintext},
            201,
        )
        token = result["token"]
        self.log_out()
        self.get(f"/shared/playlists/{token}", 404)
        self.get(f"/shared/playlists/{token}?password=wrong", 404)
        self.get(f"/shared/playlists/{token}?password={plaintext}")

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

    def test_create_guest_emits_person_new(self):
        """Connected clients (e.g. a reviewing manager) rely on the
        ``person:new`` event to learn about a freshly minted guest, so
        their personMap can resolve the person_id carried by the guest's
        first comment. Without this the comment renders blank."""
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        events.unregister_all()
        received = []

        class _Sink:
            __name__ = "guest_person_new_sink"

            def handle_event(self_sink, data):
                received.append(data)

        events.register("person:new", "guest_person_new_sink", _Sink())
        try:
            guest = self.post(
                f"/shared/playlists/{link['token']}/guest",
                {"first_name": "Lena"},
                201,
            )
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["person_id"], guest["id"])
        finally:
            events.unregister("person:new", "guest_person_new_sink")

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

    def test_create_guest_same_name_different_link(self):
        """A guest created via link A must not be reused via link B even
        if both submit the same name. Otherwise an attacker holding link B
        could impersonate any reviewer who used the same name on link A."""
        link_a = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        link_b = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        guest_a = self.post(
            f"/shared/playlists/{link_a['token']}/guest",
            {"first_name": "John", "last_name": "Smith"},
            201,
        )
        guest_b = self.post(
            f"/shared/playlists/{link_b['token']}/guest",
            {"first_name": "John", "last_name": "Smith"},
            201,
        )
        self.assertNotEqual(guest_a["id"], guest_b["id"])

    def test_reuse_guest_id_other_link_rejected(self):
        """A guest_id leaked from link A must not be reusable on link B —
        the server must ignore it and create a fresh guest instead."""
        link_a = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        link_b = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        guest_a = self.post(
            f"/shared/playlists/{link_a['token']}/guest",
            {"first_name": "Alice"},
            201,
        )
        guest_b = self.post(
            f"/shared/playlists/{link_b['token']}/guest",
            {"first_name": "Bob", "guest_id": guest_a["id"]},
            201,
        )
        self.assertNotEqual(guest_a["id"], guest_b["id"])

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

    def test_guest_comment_rejects_foreign_guest(self):
        """A guest_id from share link A cannot be replayed to post a
        comment via share link B."""
        link_a = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        link_b = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest_a = self.post(
            f"/shared/playlists/{link_a['token']}/guest",
            {"first_name": "Alice"},
            201,
        )
        self.post(
            f"/shared/playlists/{link_b['token']}/comments",
            {
                "guest_id": guest_a["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "should be rejected",
            },
            403,
        )

    def test_guest_comment_ui_built_playlist(self):
        """Shots added via the playlist builder are stored as
        ``{entity_id, preview_file_id}`` only — no ``preview_file_task_id``.
        The guest comment guard must still accept comments on the
        previewed task by deriving it from the preview file."""
        from zou.app.models.playlist import Playlist as PlaylistModel
        from zou.app.models.preview_file import PreviewFile

        preview_file = PreviewFile.create(
            name="preview.mov",
            revision=1,
            extension="mp4",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        PlaylistModel.get(self.playlist["id"]).update(
            {
                "shots": [
                    {
                        "id": str(self.asset.id),
                        "entity_id": str(self.asset.id),
                        "preview_file_id": str(preview_file.id),
                    }
                ]
            }
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
                "task_status_id": str(self.task_status.id),
                "text": "Looks good",
            },
            201,
        )

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

    # --- Share invitations ---

    def test_invite_share_link(self):
        """Manager can invite recipients by raw email and by person id;
        the response lists the dispatched, deduplicated emails."""
        from unittest.mock import patch
        from zou.app.models.person import Person

        invitee = Person.create(
            first_name="Client",
            last_name="One",
            email="client.one@example.com",
            role="client",
        )
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )

        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send_mock:
            result = self.post(
                f"/data/playlists/{self.playlist['id']}/share/{link['token']}/invite",
                {
                    "emails": [
                        "alice@example.com",
                        "ALICE@example.com",  # dedupe / case-fold
                    ],
                    "person_ids": [str(invitee.id)],
                    "message": "Please review by Friday",
                },
                200,
            )

        self.assertEqual(send_mock.call_count, 2)
        self.assertEqual(
            sorted(result["sent"]),
            ["alice@example.com", "client.one@example.com"],
        )

    def test_invite_share_link_rejects_mismatched_playlist(self):
        """A token belonging to playlist A cannot be invited via playlist B."""
        from unittest.mock import patch

        # generate_fixture_playlist mutates self.playlist as a side effect,
        # so capture the original first.
        first_playlist = self.playlist
        self.other_playlist = self.generate_fixture_playlist("Other Playlist")
        link = self.post(
            f"/data/playlists/{first_playlist['id']}/share",
            {"can_comment": True},
            201,
        )

        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send_mock:
            self.post(
                f"/data/playlists/{self.other_playlist['id']}/share/{link['token']}/invite",
                {"emails": ["alice@example.com"]},
                404,
            )
        self.assertEqual(send_mock.call_count, 0)

    def test_invite_share_link_rejects_invalid_email(self):
        """A malformed email aborts the whole batch with a 400."""
        from unittest.mock import patch

        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {"can_comment": True},
            201,
        )

        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send_mock:
            self.post(
                f"/data/playlists/{self.playlist['id']}/share/{link['token']}/invite",
                {"emails": ["not-an-email"]},
                400,
            )
        self.assertEqual(send_mock.call_count, 0)

    # --- Shared preview file downloads ---

    def _attach_zip_preview_to_playlist(self):
        """Create a non-mp4 preview file with real bytes on disk and wire
        it into the playlist's shots so that the shared preview-file
        guard recognises it."""
        import tempfile

        from zou.app.models.playlist import Playlist as PlaylistModel
        from zou.app.models.preview_file import PreviewFile
        from zou.app.stores import file_store

        preview_file = PreviewFile.create(
            name="assets.zip",
            revision=1,
            extension="zip",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        payload = b"PK\x03\x04fake-zip-payload"
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        file_store.add_file("previews", str(preview_file.id), tmp_path)
        self.addCleanup(
            file_store.remove_file, "previews", str(preview_file.id)
        )

        PlaylistModel.get(self.playlist["id"]).update(
            {
                "shots": [
                    {
                        "id": str(self.asset.id),
                        "preview_file_id": str(preview_file.id),
                        "preview_file_task_id": str(self.task.id),
                    }
                ]
            }
        )
        return preview_file, payload

    def test_shared_preview_file_download(self):
        """Any non-mp4 preview file in a shared playlist must be
        downloadable through the share link. Before this endpoint
        existed, Kitsu built the download URL on the movies/originals
        streaming path with the file's actual extension, which only
        matched ``.mp4`` and 404'd for every other extension."""
        preview_file, payload = self._attach_zip_preview_to_playlist()
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            f"/shared/playlists/{link['token']}"
            f"/preview-files/{preview_file.id}/download"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)

    def test_shared_preview_file_download_invalid_token(self):
        preview_file, _ = self._attach_zip_preview_to_playlist()
        self.log_out()
        response = self.app.get(
            f"/shared/playlists/invalid-token"
            f"/preview-files/{preview_file.id}/download"
        )
        self.assertEqual(response.status_code, 404)

    def test_shared_preview_file_download_not_in_playlist(self):
        """A preview file that is not exposed by the shared playlist
        cannot be fetched through its share link, even when the token
        is valid."""
        from zou.app.models.preview_file import PreviewFile

        foreign = PreviewFile.create(
            name="foreign.zip",
            revision=1,
            extension="zip",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            f"/shared/playlists/{link['token']}"
            f"/preview-files/{foreign.id}/download"
        )
        self.assertEqual(response.status_code, 403)

    def test_shared_preview_file_download_sibling_position(self):
        """A revision can carry multiple PreviewFile rows (different
        positions). The shared share link exposes all positions of the
        positioned revision, not only the one stored on the shot."""
        import tempfile

        from zou.app.models.playlist import Playlist as PlaylistModel
        from zou.app.models.preview_file import PreviewFile
        from zou.app.stores import file_store

        positioned, payload = self._attach_zip_preview_to_playlist()
        sibling = PreviewFile.create(
            name="sibling.zip",
            revision=positioned.revision,
            position=positioned.position + 1,
            extension="zip",
            task_id=positioned.task_id,
            person_id=self.person.id,
        )
        sibling_payload = b"PK\x03\x04sibling-position"
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(sibling_payload)
            tmp_path = tmp.name
        file_store.add_file("previews", str(sibling.id), tmp_path)
        self.addCleanup(file_store.remove_file, "previews", str(sibling.id))

        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            f"/shared/playlists/{link['token']}"
            f"/preview-files/{sibling.id}/download"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, sibling_payload)

    def test_shared_preview_file_download_other_revision_rejected(self):
        """A different revision of the same task is *not* exposed,
        only the positioned revision and its sibling positions."""
        from zou.app.models.preview_file import PreviewFile

        positioned, _ = self._attach_zip_preview_to_playlist()
        other_revision = PreviewFile.create(
            name="other.zip",
            revision=positioned.revision + 1,
            extension="zip",
            task_id=positioned.task_id,
            person_id=self.person.id,
        )
        link = self.post(
            f"/data/playlists/{self.playlist['id']}/share",
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            f"/shared/playlists/{link['token']}"
            f"/preview-files/{other_revision.id}/download"
        )
        self.assertEqual(response.status_code, 403)
