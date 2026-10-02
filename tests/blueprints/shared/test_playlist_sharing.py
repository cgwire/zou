import json
import os
import uuid

import pytest

from tests.base import ApiDBTestCase, TEST_FOLDER

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.playlist import Playlist as PlaylistModel
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.services import comments_service
from zou.app.services import entities_service
from zou.app.services import playlist_sharing_service
from zou.app.services import preview_file_states_service as states_service
from zou.app.stores import file_store
from zou.app.utils import fs

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


class SharedRevisionTestCase(PlaylistSharingTestCase):
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

    def test_a_guest_sees_no_other_revision(self):
        """
        A share link hands over the revision the playlist positions. Each
        shot also carried every revision of every task type of its entity,
        annotations included, for a revision switcher a guest does not
        have, while the file routes refuse to serve them.
        """
        payload = json.dumps(self.guest_get())

        hidden = (
            self.revision_2,
            self.layout_preview,
            self.layout_task,
            self.task_type_layout,
        )
        for row in hidden:
            self.assertNotIn(str(row.id), payload)
        self.assertNotIn("hidden-stroke", payload)

    def test_the_other_guest_routes_read_the_same_revisions(self):
        """
        The guest routes that check a comment or an attachment against the
        playlist of the link read it through get_shared_playlist, which
        still returned every revision.
        """
        link = self.post(self.share_path(), {}, 201)
        payload = json.dumps(
            playlist_sharing_service.get_shared_playlist(link["token"]),
            default=str,
        )

        for row in (self.revision_2, self.layout_preview):
            self.assertNotIn(str(row.id), payload)
        self.assertNotIn("hidden-stroke", payload)

    def test_a_guest_keeps_the_positioned_revision(self):
        """
        The player reads the positioned revision from the preview_file
        fields, with its other positions and its annotations. The revision
        list stays, empty: the player reads it on every shot.
        """
        (shot,) = self.guest_get()["shots"]

        self.assertEqual(shot["preview_file_id"], str(self.pinned.id))
        self.assertEqual(shot["preview_file_revision"], 1)
        self.assertEqual(
            shot["preview_file_task_id"], str(self.animation_task.id)
        )
        self.assertEqual(shot["preview_file_extension"], "mp4")
        self.assertEqual(
            shot["preview_file_annotations"], self.pinned_annotations
        )
        self.assertEqual(
            [preview["id"] for preview in shot["preview_file_previews"]],
            [str(self.pinned_position_2.id)],
        )
        self.assertEqual(
            shot["preview_file_task_type"]["id"],
            str(self.task_type_animation.id),
        )
        self.assertEqual((shot["name"], shot["parent_name"]), ("P01", "S01"))
        self.assertEqual(shot["preview_files"], {})

    def test_a_guest_sees_no_preview_of_another_task_of_the_type(self):
        """
        An entity can hold several tasks of one task type. The positions
        of a revision are grouped per task type, so the positioned revision
        also listed the preview of the same number on the other task,
        which the file routes refuse to serve.
        """
        # Created after the positioned revision, so it groups under it.
        retake_task = self.generate_fixture_shot_task(name="Retake")
        retake_preview = self.generate_fixture_preview_file(
            task_id=retake_task.id
        )

        (shot,) = self.guest_get()["shots"]

        self.assertEqual(
            [preview["id"] for preview in shot["preview_file_previews"]],
            [str(self.pinned_position_2.id)],
        )
        self.assertNotIn(str(retake_preview.id), json.dumps(shot))
        self.assertNotIn(str(retake_task.id), json.dumps(shot))

    def test_each_entry_of_a_repeated_entity_keeps_its_own_revision(self):
        """
        An entity can be listed several times, positioned on another
        preview each time, and every entry received the same revision
        list, which named the previews of the other entries.
        """
        self.pin(self.entry(self.pinned), self.entry(self.layout_preview))

        animation_entry, layout_entry = self.guest_get()["shots"]

        self.assertEqual(
            animation_entry["preview_file_id"], str(self.pinned.id)
        )
        self.assertEqual(
            layout_entry["preview_file_id"], str(self.layout_preview.id)
        )
        self.assertNotIn(
            str(self.layout_preview.id), json.dumps(animation_entry)
        )
        for preview in (self.pinned, self.pinned_position_2):
            self.assertNotIn(str(preview.id), json.dumps(layout_entry))
        for entry in (animation_entry, layout_entry):
            self.assertNotIn(str(self.revision_2.id), json.dumps(entry))

    def test_an_entry_without_a_live_position_exposes_no_revision(self):
        """
        An entry added before the entity had any preview, positioned on a
        preview deleted since, or stored in the legacy shape with a task
        and no preview, gets no positioned revision, and its revision list
        still named every revision of the entity.
        """
        cases = {
            "added before any preview existed": self.entry(),
            "positioned on a preview deleted since": {
                "entity_id": str(self.shot.id),
                "preview_file_id": str(uuid.uuid4()),
            },
            "stored in the legacy shape": {
                "id": str(self.shot.id),
                "preview_file_task_id": str(self.animation_task.id),
            },
        }
        previews = (
            self.pinned,
            self.pinned_position_2,
            self.revision_2,
            self.layout_preview,
        )
        for reason, entry in cases.items():
            with self.subTest(reason=reason):
                self.pin(entry)

                (shot,) = self.guest_get()["shots"]

                self.assertNotIn("preview_file_id", shot)
                payload = json.dumps(shot)
                for preview in previews:
                    self.assertNotIn(str(preview.id), payload)

    def test_the_context_lists_no_entity(self):
        """
        The context listed each entity of the playlist with its main
        preview, which can be a revision the link does not share. The
        player reads the names off the shots.
        """
        entities_service.update_entity_preview(
            str(self.shot.id), str(self.revision_2.id)
        )

        context = self.guest_get("/context")

        self.assertNotIn("entities", context)
        self.assertNotIn(str(self.revision_2.id), json.dumps(context))
        self.assertEqual(context["project"]["id"], str(self.project.id))
        self.assertIn("task_types", context)
        self.assertIn("task_statuses", context)


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

    def guest_on_a_share_link(self, can_comment=True, first_name="Reviewer"):
        """
        A share link and a guest signed in on it. Leaves the caller logged
        out, which is the state a guest works in.
        """
        link = self.post(self.share_path(), {"can_comment": can_comment}, 201)
        self.log_out()
        guest = self.post(
            self.shared_path(link["token"], "/guest"),
            {"first_name": first_name},
            201,
        )
        return link, guest

    def post_guest_comment(
        self,
        link,
        guest,
        code=201,
        text="Great work!",
        task=None,
        task_status=None,
    ):
        """
        Post a comment as a guest through a share link. The link and the
        guest are passed apart so a case can cross them over.
        """
        return self.post(
            self.shared_path(link["token"], "/comments"),
            {
                "guest_id": guest["id"],
                "task_id": str((task or self.task).id),
                "task_status_id": str((task_status or self.task_status).id),
                "text": text,
            },
            code,
        )

    def test_guest_comment(self):
        link, guest = self.guest_on_a_share_link()
        comment = self.post_guest_comment(link, guest)
        self.assertEqual(comment["text"], "Great work!")

    def test_guest_comment_rejects_foreign_guest(self):
        """
        A guest_id from share link A cannot be replayed to post a
        comment via share link B.
        """
        link_a = self.post(self.share_path(), {"can_comment": True}, 201)
        link_b = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()
        guest_a = self.post(
            self.shared_path(link_a["token"], "/guest"),
            {"first_name": "Alice"},
            201,
        )

        self.post_guest_comment(
            link_b, guest_a, code=403, text="should be rejected"
        )

    def test_guest_comment_ui_built_playlist(self):
        """
        Shots added via the playlist builder are stored as
        ``{entity_id, preview_file_id}`` only — no ``preview_file_task_id``.
        The guest comment guard must still accept comments on the
        previewed task by deriving it from the preview file.
        """

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
        link, guest = self.guest_on_a_share_link()
        self.post_guest_comment(link, guest, text="Looks good")

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
        link, guest = self.guest_on_a_share_link()
        self.post_guest_comment(
            link, guest, code=403, text="should be rejected", task=foreign_task
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
        link, guest = self.guest_on_a_share_link()
        self.post_guest_comment(
            link,
            guest,
            code=400,
            text="should be rejected",
            task_status=manager_status,
        )

    def test_guest_comment_disabled(self):
        link, guest = self.guest_on_a_share_link(can_comment=False)
        self.post_guest_comment(link, guest, code=403, text="Should fail")

    def _guest_comment(self, first_name="Reviewer"):
        """
        A share link that allows comments, a guest on it, and one comment
        posted by that guest.
        """
        link, guest = self.guest_on_a_share_link(first_name=first_name)
        return link, guest, self.post_guest_comment(link, guest)

    def test_guest_edits_own_comment(self):
        link, guest, comment = self._guest_comment()

        result = self.put(
            f"/shared/playlists/{link['token']}/comments/{comment['id']}",
            {"guest_id": guest["id"], "text": "Second thought"},
            200,
        )
        self.assertEqual(result["text"], "Second thought")

    def test_an_edited_comment_keeps_naming_its_repliers(self):
        link, guest, comment = self._guest_comment()
        comments_service.reply_comment(
            comment["id"], "Noted", person_id=str(self.user["id"])
        )

        result = self.put(
            self.shared_path(link["token"], f"/comments/{comment['id']}"),
            {"guest_id": guest["id"], "text": "Second thought"},
        )

        replier = result["replies"][0]["person"]
        self.assertEqual(replier["id"], str(self.user["id"]))

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

    def test_the_comment_list_carries_guest_attachments(self):
        """
        The list is what the page reloads from: an attachment missing there
        vanished from the comment, although its download route serves it.
        """
        link, guest, comment = self._guest_comment()
        attachment = self._attach_to_guest_comment(link, guest, comment)[
            "attachment_files"
        ][0]

        comments = self.get(self.shared_path(link["token"], "/comments"))

        listed = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(
            [a["id"] for a in listed["attachment_files"]], [attachment["id"]]
        )
        self.assertEqual(listed["attachment_files"][0]["name"], "th01.png")

    def test_the_comment_list_carries_client_comment_attachments(self):
        comment = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            "See the reference",
            for_client=True,
        )
        attachment = AttachmentFile.create(
            name="reference.png",
            extension="png",
            mimetype="image/png",
            comment_id=comment["id"],
        )
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        comments = self.get(self.shared_path(link["token"], "/comments"))

        listed = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(
            [a["id"] for a in listed["attachment_files"]],
            [str(attachment.id)],
        )

    def test_the_comment_list_leaves_internal_attachments_out(self):
        """
        Only the comments the link shows bring their files: the attachment
        of an internal comment on the same task stays with the studio.
        """
        internal = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            "Studio only",
        )
        internal_attachment = AttachmentFile.create(
            name="internal.png",
            extension="png",
            mimetype="image/png",
            comment_id=internal["id"],
        )
        visible = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            "Looks good",
            for_client=True,
        )
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        comments = self.get(self.shared_path(link["token"], "/comments"))

        self.assertNotIn(internal["id"], [c["id"] for c in comments])
        self.assertNotIn(
            str(internal_attachment.id),
            [a["id"] for c in comments for a in c["attachment_files"]],
        )
        listed = next(c for c in comments if c["id"] == visible["id"])
        self.assertEqual(listed["attachment_files"], [])

    def test_the_comment_list_names_the_repliers(self):
        comment = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            "Looks good",
            for_client=True,
        )
        comments_service.reply_comment(
            comment["id"], "Thanks", person_id=str(self.user["id"])
        )
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        comments = self.get(self.shared_path(link["token"], "/comments"))

        listed = next(c for c in comments if c["id"] == comment["id"])
        replier = listed["replies"][0]["person"]
        self.assertEqual(replier["id"], str(self.user["id"]))
        self.assertEqual(replier["full_name"], "John Did")

    def test_a_missing_attachment_file_answers_404(self):
        """
        The page of the link loads every picture, sound and movie its
        comment list names: a file gone from the storage is not found, as
        on the studio route, rather than a server error.
        """
        comment = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            "See the reference",
            for_client=True,
        )
        attachment = AttachmentFile.create(
            name="reference.png",
            extension="png",
            mimetype="image/png",
            comment_id=comment["id"],
        )
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        response = self.app.get(
            self.shared_path(
                link["token"],
                f"/attachment-files/{attachment.id}/file/reference.png",
            )
        )
        self.assertEqual(response.status_code, 404)

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


class SharedAvatarTestCase(PlaylistSharingTestCase):
    """
    The avatars a link serves: those of the people its page shows, the
    authors of the comments it lists and of their replies, and nobody else.
    """

    def tearDown(self):
        super().tearDown()
        fs.rm_rf(TEST_FOLDER)

    def give_an_avatar(self, person_id):
        self.upload_file(
            f"/pictures/thumbnails/persons/{person_id}",
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
        )

    def get_avatar(self, link, person_id):
        return self.app.get(
            self.shared_path(
                link["token"], f"/pictures/thumbnails/persons/{person_id}.png"
            )
        )

    def new_comment(self, text, for_client=False):
        return comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.person.id),
            text,
            for_client=for_client,
        )

    def test_a_link_serves_the_avatars_of_the_people_it_shows(self):
        comment = self.new_comment("Looks good", for_client=True)
        comments_service.reply_comment(
            comment["id"], "Thanks", person_id=str(self.user["id"])
        )
        self.give_an_avatar(self.person.id)
        self.give_an_avatar(self.user["id"])
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        for person_id in (self.person.id, self.user["id"]):
            response = self.get_avatar(link, person_id)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "image/png")

    def test_a_playlist_built_in_kitsu_serves_the_avatars(self):
        # The playlist builder stores the positioned preview of a shot, not
        # its task.
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
        self.new_comment("Looks good", for_client=True)
        self.give_an_avatar(self.person.id)
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        self.assertEqual(
            self.get_avatar(link, self.person.id).status_code, 200
        )

    def test_a_link_keeps_the_other_avatars(self):
        self.new_comment("Studio only")
        self.give_an_avatar(self.person.id)
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        self.assertEqual(
            self.get_avatar(link, self.person.id).status_code, 404
        )

    def test_a_shown_person_without_avatar_answers_404(self):
        self.new_comment("Looks good", for_client=True)
        link = self.post(self.share_path(), {"can_comment": True}, 201)
        self.log_out()

        self.assertEqual(
            self.get_avatar(link, self.person.id).status_code, 404
        )


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

        preview_file = PreviewFile.create(
            name="assets.zip",
            revision=1,
            extension="zip",
            task_id=self.task.id,
            person_id=self.person.id,
            status="ready",
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

        positioned, payload = self._attach_zip_preview_to_playlist()
        sibling = PreviewFile.create(
            name="sibling.zip",
            revision=positioned.revision,
            position=positioned.position + 1,
            extension="zip",
            task_id=positioned.task_id,
            person_id=self.person.id,
            status="ready",
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

        preview_file = PreviewFile.create(
            name="loop.gif",
            revision=1,
            extension="gif",
            task_id=self.task.id,
            person_id=self.person.id,
            status="ready",
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

        preview_file = PreviewFile.create(
            name="still.png",
            revision=1,
            extension="png",
            task_id=self.task.id,
            person_id=self.person.id,
            status="ready",
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
        file is absent from storage yields a 404, not a 500, and the
        confirmed absence is recorded.
        """

        preview_file = PreviewFile.create(
            name="gone.gif",
            revision=1,
            extension="gif",
            task_id=self.task.id,
            person_id=self.person.id,
            status="ready",
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
        # Reached the storage lookup (not the processing short-circuit):
        # the confirmed absence is recorded. A non-png extension is
        # served through send_preview_standard_file, bucket "files".
        states = states_service.get_file_states(str(preview_file.id))
        self.assertEqual(
            states_service.get_state(states, "files", "previews"),
            "missing",
        )
