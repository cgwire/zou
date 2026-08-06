import pytest

from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.playlist import Playlist as PlaylistModel
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.stores import file_store

# Share-link passwords are hashed with bcrypt; the verification path must
# not be patched to always-True here.
pytestmark = pytest.mark.real_bcrypt


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


class ShareLinkTestCase(PlaylistSharingTestCase):
    """
    Creating, listing, revoking and inviting to a share link, all of
    which a manager of the production does.
    """

    def test_create_share_link(self):
        result = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.assertIsNotNone(result["token"])
        self.assertTrue(result["is_active"])
        self.assertTrue(result["can_comment"])

    def test_list_share_links(self):
        self.post(
            self.share_path(),
            {},
            201,
        )
        result = self.get(self.share_path())
        self.assertEqual(len(result), 1)

    def test_share_link_routes_check_project_access(self):
        """
        A manager who is not on the playlist's project must not be
        able to list, create, or revoke share links for that playlist
        (cross-project IDOR).
        """
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )

        self.generate_fixture_user_manager()
        self.log_out()
        self.log_in_manager()

        self.get(self.share_path(), 403)
        self.post(
            self.share_path(),
            {"can_comment": True},
            403,
        )
        self.delete(
            self.share_path(link["token"]),
            403,
        )

    def test_revoke_share_link_rejects_mismatched_playlist(self):
        """
        A token must only be revocable through the URL of the playlist
        it actually belongs to. Otherwise an admin/manager who knows any
        token could revoke it via any playlist URL they have access to.
        """

        other_playlist = Playlist.create(
            name="Other Playlist",
            project_id=self.project.id,
            for_entity="shot",
            shots=[],
        ).serialize()

        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.delete(
            f"/data/playlists/{other_playlist['id']}/share/{link['token']}",
            404,
        )

    def test_share_link_password_is_hashed_and_not_serialized(self):
        """
        Manager-facing endpoints must never return the share link
        password, and the value stored at rest must be a bcrypt hash, not
        plaintext.
        """

        plaintext = "topsecret123"
        result = self.post(
            self.share_path(),
            {"password": plaintext},
            201,
        )
        self.assertNotIn("password", result)
        self.assertTrue(result.get("has_password"))

        listing = self.get(self.share_path())
        self.assertEqual(len(listing), 1)
        self.assertNotIn("password", listing[0])
        self.assertTrue(listing[0].get("has_password"))

        stored = PlaylistShareLink.get_by(token=result["token"])
        self.assertIsNotNone(stored.password)
        self.assertNotEqual(stored.password, plaintext)
        self.assertTrue(stored.password.startswith("$2"))

    def test_share_link_password_validates_with_bcrypt(self):
        """
        The shared playlist endpoint must accept the correct password
        (verified against the bcrypt hash) and reject incorrect ones.
        """
        plaintext = "topsecret123"
        result = self.post(
            self.share_path(),
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
            self.share_path(),
            {},
            201,
        )
        self.delete(
            self.share_path(link["token"]),
            200,
        )
        result = self.get(self.share_path())
        self.assertEqual(result, [])

    def test_invite_share_link(self):
        """
        Manager can invite recipients by raw email and by person id;
        the response lists the dispatched, deduplicated emails.
        """
        from unittest.mock import patch

        invitee = Person.create(
            first_name="Client",
            last_name="One",
            email="client.one@example.com",
            role="client",
        )
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )

        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send_mock:
            result = self.post(
                self.share_path(link["token"], "/invite"),
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
        """
        A token belonging to playlist A cannot be invited via playlist B.
        """
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
        """
        A malformed email aborts the whole batch with a 400.
        """
        from unittest.mock import patch

        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )

        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send_mock:
            self.post(
                self.share_path(link["token"], "/invite"),
                {"emails": ["not-an-email"]},
                400,
            )
        self.assertEqual(send_mock.call_count, 0)


class SharedPlaylistReadTestCase(PlaylistSharingTestCase):
    """
    What the viewer behind the link reads, and the tokens that give
    them nothing.
    """

    def test_get_shared_playlist(self):
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        result = self.get(self.shared_path(link["token"]))
        self.assertEqual(result["id"], self.playlist["id"])

    def test_get_shared_playlist_invalid_token(self):
        self.log_out()
        self.get("/shared/playlists/invalid-token", 404)

    def test_get_shared_playlist_revoked(self):
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.delete(
            self.share_path(link["token"]),
            200,
        )
        self.log_out()
        self.get(self.shared_path(link["token"]), 404)

    def test_get_shared_playlist_context(self):
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        result = self.get(self.shared_path(link["token"], "/context"))
        self.assertIn("project", result)
        self.assertIn("task_types", result)
        self.assertIn("task_statuses", result)


class GuestTestCase(PlaylistSharingTestCase):
    """
    The person record a viewer gets on first arrival, reused on the
    next visit and scoped to the link that created it.
    """

    def test_create_guest(self):
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "John", "last_name": "Doe"},
            201,
        )
        self.assertEqual(guest["first_name"], "John")
        self.assertTrue(guest["is_guest"])

    def test_create_guest_emits_person_new(self):
        """
        Connected clients (e.g. a reviewing manager) rely on the
        ``person:new`` event to learn about a freshly minted guest, so
        their personMap can resolve the person_id carried by the guest's
        first comment. Without this the comment renders blank.
        """
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        received = self.capture_events("person:new")
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Lena"},
            201,
        )
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["person_id"], guest["id"])

    def test_reuse_guest(self):
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "John"},
            201,
        )
        guest2 = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Jane", "guest_id": guest["id"]},
            200,
        )
        self.assertEqual(guest["id"], guest2["id"])

    def test_create_guest_same_name_different_link(self):
        """
        A guest created via link A must not be reused via link B even
        if both submit the same name. Otherwise an attacker holding link B
        could impersonate any reviewer who used the same name on link A.
        """
        link_a = self.post(
            self.share_path(),
            {},
            201,
        )
        link_b = self.post(
            self.share_path(),
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
        """
        A guest_id leaked from link A must not be reusable on link B —
        the server must ignore it and create a fresh guest instead.
        """
        link_a = self.post(
            self.share_path(),
            {},
            201,
        )
        link_b = self.post(
            self.share_path(),
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


class GuestCommentTestCase(PlaylistSharingTestCase):
    """
    Commenting as a guest, and everything that must be refused: a
    foreign guest, a task outside the playlist, a status the client
    may not set, another guest's comment or attachment.
    """

    def test_guest_comment(self):
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Reviewer"},
            201,
        )
        comment = self.post(
            self.shared_path(link["token"], "/comments"),
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
        """
        A guest_id from share link A cannot be replayed to post a
        comment via share link B.
        """
        link_a = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        link_b = self.post(
            self.share_path(),
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
        """
        Shots added via the playlist builder are stored as
        ``{entity_id, preview_file_id}`` only — no ``preview_file_task_id``.
        The guest comment guard must still accept comments on the
        previewed task by deriving it from the preview file.
        """
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
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "Looks good",
            },
            201,
        )

    def test_guest_comment_rejects_foreign_task(self):
        """
        A guest cannot post a comment on a task that is not part of the
        playlist they hold a share link to.
        """

        foreign_task = Task.create(
            name="Foreign",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
        )
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str(foreign_task.id),
                "task_status_id": str(self.task_status.id),
                "text": "should be rejected",
            },
            403,
        )

    def test_guest_comment_rejects_non_client_status(self):
        """
        A guest cannot set a task status that is not client-allowed.
        """

        manager_status = TaskStatus.create(
            name="Approved",
            short_name="apr",
            color="#000000",
            is_client_allowed=False,
        )
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            self.shared_path(link["token"], "/comments"),
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
            self.share_path(),
            {"can_comment": False},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Reviewer"},
            201,
        )
        self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "Should fail",
            },
            403,
        )

    def _guest_comment(self, first_name="Reviewer"):
        """
        A share link that allows comments, a guest on it, and one comment
        posted by that guest.
        """
        link = self.post(
            self.share_path(),
            {"can_comment": True},
            201,
        )
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": first_name},
            201,
        )
        comment = self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "Great work!",
            },
            201,
        )
        return link, guest, comment

    def test_guest_edits_own_comment(self):
        link, guest, comment = self._guest_comment()

        result = self.put(
            f"/shared/playlists/{link['token']}/comments/{comment['id']}",
            {"guest_id": guest["id"], "text": "Second thought"},
            200,
        )
        self.assertEqual(result["text"], "Second thought")

    def test_guest_deletes_own_comment(self):
        link, guest, comment = self._guest_comment()
        path = f"/shared/playlists/{link['token']}/comments/{comment['id']}"

        response = self.app.delete(path, json={"guest_id": guest["id"]})
        self.assertEqual(response.status_code, 204)

        # Gone is 404, someone else's is 403: the loader tells the two apart
        # so a guest cannot probe for comments they do not own.
        response = self.app.delete(path, json={"guest_id": guest["id"]})
        self.assertEqual(response.status_code, 404)

    def test_guest_cannot_touch_another_guest_comment(self):
        """
        The guest id travels in the body, so nothing stops a reviewer from
        naming someone else's. The comment has to belong to the guest that
        claims it, on that very share link.
        """
        link, _, comment = self._guest_comment("Alice")
        other = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": "Bob"},
            201,
        )
        path = f"/shared/playlists/{link['token']}/comments/{comment['id']}"

        self.put(path, {"guest_id": other["id"], "text": "hijacked"}, 403)

        response = self.app.delete(path, json={"guest_id": other["id"]})
        self.assertEqual(response.status_code, 403)

    def _attach_to_guest_comment(self, link, guest, comment):
        import os

        fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        response = self.app.post(
            self.shared_path(
                link["token"], f"/comments/{comment['id']}/attachments"
            ),
            data={
                "file": (open(fixture, "rb"), "th01.png"),
                "guest_id": guest["id"],
            },
        )
        self.assertEqual(response.status_code, 201, response.data[:200])
        return response.json

    def test_guest_attaches_a_file_to_own_comment(self):
        link, guest, comment = self._guest_comment()

        result = self._attach_to_guest_comment(link, guest, comment)
        self.assertEqual(len(result["attachment_files"]), 1)
        self.assertEqual(result["attachment_files"][0]["name"], "th01.png")

    def test_guest_removes_own_attachment(self):
        link, guest, comment = self._guest_comment()
        attachment = self._attach_to_guest_comment(link, guest, comment)[
            "attachment_files"
        ][0]

        response = self.app.delete(
            f"/shared/playlists/{link['token']}/comments/{comment['id']}"
            f"/attachments/{attachment['id']}",
            json={"guest_id": guest["id"]},
        )
        self.assertEqual(response.status_code, 204)

    def test_guest_cannot_remove_an_attachment_of_another_comment(self):
        """
        Three ids travel together here, and owning the comment is not enough:
        the attachment has to hang from that very comment, otherwise naming
        one's own comment would remove any attachment at all.
        """
        link, guest, comment = self._guest_comment()
        other_comment = self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "second comment",
            },
            201,
        )
        attachment = self._attach_to_guest_comment(link, guest, other_comment)[
            "attachment_files"
        ][0]

        response = self.app.delete(
            f"/shared/playlists/{link['token']}/comments/{comment['id']}"
            f"/attachments/{attachment['id']}",
            json={"guest_id": guest["id"]},
        )
        self.assertEqual(response.status_code, 404)


class SharedFileServingTestCase(PlaylistSharingTestCase):
    """
    Serving the preview binaries through the link. Only the previews
    the playlist positions are served, and only the extensions that
    are safe to render.
    """

    def _attach_zip_preview_to_playlist(self):
        """
        Create a non-mp4 preview file with real bytes on disk and wire
        it into the playlist's shots so that the shared preview-file
        guard recognises it.
        """
        import tempfile

        from zou.app.models.preview_file import PreviewFile

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
        """
        Any non-mp4 preview file in a shared playlist must be
        downloadable through the share link. Before this endpoint
        existed, Kitsu built the download URL on the movies/originals
        streaming path with the file's actual extension, which only
        matched ``.mp4`` and 404'd for every other extension.
        """
        preview_file, payload = self._attach_zip_preview_to_playlist()
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"], f"/preview-files/{preview_file.id}/download"
            )
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

    def test_a_preview_the_playlist_does_not_carry_is_refused(self):
        """
        A valid share token opens the playlist, not the production behind
        it: a preview file the playlist does not carry stays out, whichever
        route asks for it.
        """
        link = self.post(self.share_path(), {}, 201)
        self.log_out()
        cases = {
            "the download route": (
                "zip",
                "/preview-files/{id}/download",
            ),
            "the originals route": (
                "gif",
                "/pictures/originals/preview-files/{id}.gif",
            ),
        }
        for reason, (extension, suffix) in cases.items():
            with self.subTest(reason=reason):
                foreign = PreviewFile.create(
                    name=f"foreign.{extension}",
                    revision=1,
                    extension=extension,
                    task_id=self.task.id,
                    person_id=self.person.id,
                )
                response = self.app.get(
                    self.shared_path(
                        link["token"], suffix.format(id=foreign.id)
                    )
                )
                self.assertEqual(response.status_code, 403)

    def test_shared_preview_file_download_sibling_position(self):
        """
        A revision can carry multiple PreviewFile rows (different
        positions). The shared share link exposes all positions of the
        positioned revision, not only the one stored on the shot.
        """
        import tempfile

        from zou.app.models.preview_file import PreviewFile

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
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"], f"/preview-files/{sibling.id}/download"
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, sibling_payload)

    def test_shared_preview_file_download_other_revision_rejected(self):
        """
        A different revision of the same task is *not* exposed,
        only the positioned revision and its sibling positions.
        """

        positioned, _ = self._attach_zip_preview_to_playlist()
        other_revision = PreviewFile.create(
            name="other.zip",
            revision=positioned.revision + 1,
            extension="zip",
            task_id=positioned.task_id,
            person_id=self.person.id,
        )
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"], f"/preview-files/{other_revision.id}/download"
            )
        )
        self.assertEqual(response.status_code, 403)

    def _attach_gif_preview_to_playlist(self):
        """
        Create an animated-GIF still preview with real bytes on disk and
        wire it into the playlist's shots, the way an uploaded GIF is
        stored (under the ``previews`` prefix, extension ``gif``).
        """
        import tempfile

        from zou.app.models.preview_file import PreviewFile

        preview_file = PreviewFile.create(
            name="loop.gif",
            revision=1,
            extension="gif",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        payload = b"GIF89a-fake-animated-payload"
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
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

    def test_shared_original_gif(self):
        """
        A GIF still preview in a shared playlist must be served through
        the originals picture path. The ``.png``-only shared route did
        not match ``.gif`` (or any non-PNG extension), so animated GIFs
        404'd through a share link.
        """
        preview_file, payload = self._attach_gif_preview_to_playlist()
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"],
                f"/pictures/originals/preview-files/{preview_file.id}.gif",
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)

    def test_shared_original_extension_not_allowed(self):
        """
        Disallowed extensions are rejected with a 400, mirroring the
        authenticated generic originals route.
        """
        preview_file, _ = self._attach_gif_preview_to_playlist()
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"],
                f"/pictures/originals/preview-files/{preview_file.id}.exe",
            )
        )
        self.assertEqual(response.status_code, 400)

    def test_shared_original_png_still_served(self):
        """
        Regression guard: the static ``.png`` originals route must keep
        winning over the new generic ``.<extension>`` route, and a PNG
        original (stored under the ``original`` picture prefix) is served.
        """
        import tempfile

        from zou.app.models.preview_file import PreviewFile

        preview_file = PreviewFile.create(
            name="still.png",
            revision=1,
            extension="png",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        payload = b"\x89PNG\r\n\x1a\n-fake-original-png"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        file_store.add_picture("original", str(preview_file.id), tmp_path)
        self.addCleanup(
            file_store.remove_picture, "original", str(preview_file.id)
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
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"],
                f"/pictures/originals/preview-files/{preview_file.id}.png",
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, payload)

    def test_shared_original_missing_file(self):
        """
        A preview that is part of the shared playlist but whose original
        file is absent from storage yields a 404, not a 500.
        """
        from zou.app.models.preview_file import PreviewFile

        preview_file = PreviewFile.create(
            name="gone.gif",
            revision=1,
            extension="gif",
            task_id=self.task.id,
            person_id=self.person.id,
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
        link = self.post(
            self.share_path(),
            {},
            201,
        )
        self.log_out()
        response = self.app.get(
            self.shared_path(
                link["token"],
                f"/pictures/originals/preview-files/{preview_file.id}.gif",
            )
        )
        self.assertEqual(response.status_code, 404)
