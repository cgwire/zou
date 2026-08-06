import datetime

from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task

from zou.app.services import comments_service, playlist_sharing_service
from zou.app.services.exception import (
    PlaylistShareLinkNotFoundException,
    WrongParameterException,
)
from zou.app.services.playlist_sharing_service import GuestCommentNotFound


class SharedPlaylistTestCase(ApiDBTestCase):
    """
    One production, one asset carrying a task, and a playlist to share.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.playlist = self.generate_fixture_playlist("Test Playlist")

    def share(self, **kwargs):
        """
        Share the playlist and return the token a viewer would be given.
        """
        link = playlist_sharing_service.create_share_link(
            self.playlist["id"], self.person.id, **kwargs
        )
        return link["token"]

    def position(self, *shots):
        """
        Set the playlist shot list. The playlist builder stores no more
        than entity_id and preview_file_id per shot.
        """
        Playlist.get(self.playlist["id"]).update({"shots": list(shots)})

    def preview(self, task=None, revision=1, position=1):
        # (name, task_id, revision) is unique, and the fixtures hold two
        # positions of one revision, so the position names the file too.
        return PreviewFile.create(
            name=f"preview-{revision}-{position}.png",
            revision=revision,
            position=position,
            extension="png",
            task_id=(task or self.task).id,
            person_id=self.person.id,
        )


class ShareTokenTestCase(SharedPlaylistTestCase):
    """
    The token is the whole credential of an unauthenticated viewer, so
    what makes it stop working is what makes the link safe.
    """

    def expires_on(self, expiration_date):
        return PlaylistShareLink.get_by(
            token=self.share(expiration_date=expiration_date)
        ).expiration_date

    def test_a_link_without_expiration_date_never_expires(self):
        self.assertIsNone(self.expires_on(None))
        self.assertIsNone(self.expires_on(""))

    def test_a_link_expires_at_the_end_of_the_day_it_names(self):
        """
        The date a manager picks names a whole day, and Kitsu displays it
        as such. A link set to expire today therefore has to work today:
        pinning the expiration to the first second of that day killed it
        a full day before the date shown next to it.
        """
        today = datetime.date.today()
        token = self.share(expiration_date=today.isoformat())

        self.assertEqual(
            PlaylistShareLink.get_by(token=token).expiration_date,
            datetime.datetime.combine(today, datetime.time.max),
        )
        playlist_sharing_service.validate_share_token(token)

    def test_a_link_expires_once_its_day_is_over(self):
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        token = self.share(expiration_date=yesterday.isoformat())
        self.assertRaises(
            PlaylistShareLinkNotFoundException,
            playlist_sharing_service.validate_share_token,
            token,
        )

    def test_an_expiration_timestamp_is_honoured_as_given(self):
        """
        A full timestamp says the hour it means, so it is not pushed to
        the end of the day the way a bare date is.
        """
        moment = datetime.datetime(2030, 1, 2, 3, 4, 5)
        self.assertEqual(self.expires_on(moment.isoformat()), moment)

    def test_an_unparsable_expiration_date_is_a_bad_request(self):
        """
        The date reaches the service straight from the request body. It
        used to be read at one single format, so any other one raised a
        ValueError out of the resource and answered a 500.
        """
        self.assertRaises(
            WrongParameterException,
            self.share,
            expiration_date="tomorrow",
        )

    def test_an_expiration_read_from_a_naive_column_is_taken_as_utc(self):
        """
        The column is timezone naive, while the comparison is made in
        UTC. Reading a naive expiration as local time would open or shut
        the link an offset early depending on where the server runs.
        """
        token = self.share()
        PlaylistShareLink.get_by(token=token).update(
            {
                "expiration_date": datetime.datetime.now(
                    datetime.timezone.utc
                ).replace(tzinfo=None)
                + datetime.timedelta(minutes=5)
            }
        )
        playlist_sharing_service.validate_share_token(token)

    def test_a_revoked_link_stops_answering(self):
        token = self.share()
        playlist_sharing_service.validate_share_token(token)

        playlist_sharing_service.revoke_share_link(token)
        self.assertRaises(
            PlaylistShareLinkNotFoundException,
            playlist_sharing_service.validate_share_token,
            token,
        )
        # Revoking deactivates rather than deletes, so the row is still
        # there to be told apart from a token that never existed.
        self.assertIsNotNone(PlaylistShareLink.get_by(token=token))

    def test_a_revoked_link_invites_nobody(self):
        """
        The invitation is sent by a manager rather than read by a viewer,
        so it carries a guard of its own: mailing a link that no longer
        opens would send a reviewer a URL that answers 404.
        """
        token = self.share()
        playlist_sharing_service.revoke_share_link(token)
        with patch(
            "zou.app.services.emails_service.send_share_invitation"
        ) as send:
            self.assertRaises(
                PlaylistShareLinkNotFoundException,
                playlist_sharing_service.send_share_invitations,
                self.playlist["id"],
                token,
                self.person.id,
                emails=["reviewer@example.com"],
            )
        send.assert_not_called()

    def test_an_unknown_token_is_not_found(self):
        self.assertRaises(
            PlaylistShareLinkNotFoundException,
            playlist_sharing_service.validate_share_token,
            "no-such-token",
        )


class SharedPlaylistMembershipTestCase(SharedPlaylistTestCase):
    """
    Which preview files a share link is allowed to serve. Every
    file-serving endpoint of the shared player asks this one question.
    """

    def test_membership_same_entity_in_several_shots(self):
        """
        A playlist may list the same entity several times, each shot
        positioned on a different task type and a different revision (e.g.
        one task pinned to revision 2 and another to revision 1). Every
        positioned preview must pass the shared-playlist membership check,
        not only the last shot's. Before the fix the check collapsed the
        shots into a single entity -> preview_file_id mapping (regression
        from 54ec061ce): only the last shot's preview, and any preview
        sharing its revision number, was served, so the revision 2 preview
        returned 403 while the revision 1 one (matching the last shot)
        worked.

        The two shots are pinned to *different* revisions on purpose: with
        equal revisions the old code let the non-last preview through by
        coincidence and the regression would slip past this test.
        """
        # Two task types positioned on the SAME asset, on different revisions.
        first_task = self.task
        second_task = Task.create(
            name="Second",
            project_id=self.project.id,
            task_type_id=self.task_type_modeling.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assigner_id=self.assigner.id,
        )
        first_preview = self.preview(first_task, revision=2)
        second_preview = self.preview(second_task, revision=1)
        self.position(
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(first_preview.id),
            },
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(second_preview.id),
            },
        )
        token = self.share()

        # Both positioned previews belong to the shared playlist. The first
        # shot's preview (revision 2) used to be overwritten in the entity
        # map by the last shot (revision 1) and 403'd.
        self.assertTrue(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(first_preview.id)
            )
        )
        self.assertTrue(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(second_preview.id)
            )
        )

        # A sibling position of a positioned revision is still accepted
        # (same task, same revision, different position).
        sibling = self.preview(
            first_task,
            revision=first_preview.revision,
            position=first_preview.position + 1,
        )
        self.assertTrue(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(sibling.id)
            )
        )

        # A different revision of a positioned task stays rejected.
        other_revision = self.preview(
            first_task, revision=first_preview.revision + 1
        )
        self.assertFalse(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(other_revision.id)
            )
        )

        # A preview on a DIFFERENT positioned task that merely shares another
        # positioned preview's revision NUMBER stays rejected: membership is
        # decided on (task_id, revision), not on the revision number alone.
        # This is the case the (task_id) guard exists for; without it the
        # revision-only comparison would wrongly accept it.
        cross_task_collision = self.preview(
            # Revision 2, the number first_preview carries, but on the other
            # (also positioned) task.
            second_task,
            revision=first_preview.revision,
        )
        self.assertFalse(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(cross_task_collision.id)
            )
        )

    def test_membership_of_a_preview_of_an_entity_outside_the_playlist(self):
        """
        Positioning nothing of an entity means serving nothing of it,
        whatever revision the caller asks for.
        """
        self.position()
        token = self.share()
        self.assertFalse(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(self.preview().id)
            )
        )

    def test_membership_skips_dangling_positioned_preview(self):
        """
        A playlist shot keeps its preview_file_id even after that preview is
        deleted (deletion does not scrub playlist.shots). The membership
        check must skip such a dangling positioned id and answer cleanly,
        instead of raising PreviewFileNotFoundException and turning a
        legitimate response into a 404.
        """
        positioned = self.preview(revision=1)
        # Another, non-positioned preview of the same entity, on a different
        # revision, so it is not a member.
        other = self.preview(revision=2)
        self.position(
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(positioned.id),
            }
        )
        token = self.share()

        # Delete the positioned preview, leaving a dangling id in the shot.
        PreviewFile.get(positioned.id).delete()

        # The loop dereferences the dangling positioned id; it must be skipped
        # rather than raising, so the check returns False cleanly.
        self.assertFalse(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(other.id)
            )
        )


class SharedPlaylistReadTestCase(SharedPlaylistTestCase):
    """
    What the viewer behind the link reads. They hold no token for the
    entity, project or task stores, so every name and colour the player
    shows has to be inlined in the playlist itself.
    """

    def enrich(self, *shots):
        return playlist_sharing_service.enrich_shots_with_entity_info(
            {"project_id": str(self.project.id), "shots": list(shots)}
        )

    def test_get_shared_playlist(self):
        """
        Shots come back enriched with the task the positioned preview
        belongs to, which the raw playlist.shots JSON does not carry.
        """
        preview = self.preview()
        self.position(
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(preview.id),
            }
        )
        token = self.share()

        playlist = playlist_sharing_service.get_shared_playlist(token)
        self.assertEqual(playlist["id"], self.playlist["id"])
        self.assertEqual(
            playlist["shots"][0]["preview_file_task_id"], str(self.task.id)
        )

        playlist_sharing_service.revoke_share_link(token)
        self.assertRaises(
            PlaylistShareLinkNotFoundException,
            playlist_sharing_service.get_shared_playlist,
            token,
        )

    def test_the_project_line_is_inlined(self):
        self.project.update({"fps": "24"})
        result = self.enrich()
        self.assertEqual(result["project_name"], self.project.name)
        self.assertEqual(result["project_fps"], "24")

    def test_an_entity_is_named_and_placed_under_its_kind(self):
        """
        Assets are not shot-like, so what the player shows above the name
        is the asset type rather than a parent record.
        """
        (shot,) = self.enrich({"id": str(self.asset.id)})["shots"]
        self.assertEqual(shot["name"], self.asset.name)
        self.assertEqual(shot["parent_name"], self.asset_type.name)

    def test_a_shot_is_placed_under_its_sequence(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        (shot,) = self.enrich({"id": str(self.shot.id)})["shots"]
        self.assertEqual(shot["name"], self.shot.name)
        self.assertEqual(shot["parent_name"], self.sequence.name)

    def test_a_shot_like_entity_without_a_parent_is_placed_nowhere(self):
        """
        A sequence of a production that has no episodes has no parent
        record to name, and the asset type fallback would read as one.
        """
        self.generate_fixture_sequence()
        (shot,) = self.enrich({"id": str(self.sequence.id)})["shots"]
        self.assertEqual(shot["parent_name"], "")

    def test_the_task_type_and_status_colours_are_inlined(self):
        self.task_type.update({"color": "#111111"})
        self.task_status.update({"color": "#222222"})
        (shot,) = self.enrich(
            {
                "id": str(self.asset.id),
                "preview_file_task_id": str(self.task.id),
            }
        )["shots"]
        self.assertEqual(shot["preview_file_task_type_name"], "Shaders")
        self.assertEqual(shot["preview_file_task_type"]["color"], "#111111")
        self.assertEqual(shot["task_status_color"], "#222222")

    def test_a_shot_of_a_deleted_entity_is_left_alone(self):
        """
        Deleting an entity does not scrub the playlists holding it, so the
        enrichment walks over ids it cannot resolve.
        """
        (shot,) = self.enrich({"id": str(self.person.id)})["shots"]
        self.assertNotIn("name", shot)

    def test_a_playlist_built_from_the_builder_is_enriched_too(self):
        """
        The builder stores entity_id where the rest of the pipeline reads
        id, and the enrichment reads id only. It is get_playlist_with_
        preview_file_revisions that reconciles the two upstream, so the
        two functions are only correct together.
        """
        preview = self.preview()
        self.position(
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(preview.id),
            }
        )
        playlist = playlist_sharing_service.enrich_shots_with_entity_info(
            playlist_sharing_service.get_shared_playlist(self.share())
        )
        self.assertEqual(playlist["shots"][0]["name"], self.asset.name)


class SharedCommentTestCase(SharedPlaylistTestCase):
    """
    Comments and attachments served through the link. This is the one
    unauthenticated read path into a production's discussion, so what it
    hides matters more than what it shows.
    """

    def comment(self, person=None, **fields):
        comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            (person or self.person).id,
            "look at this",
            **fields,
        )
        return Comment.get(comment["id"])

    def guest(self):
        return Person.create(
            first_name="Reviewer",
            last_name="One",
            email="reviewer@guest.kitsu",
            role="client",
            is_guest=True,
        )

    def test_only_client_and_guest_comments_are_shared(self):
        """
        The query behind this reads every comment of the task: a client
        gets no filtering from _prepare_query, so the whole visibility
        rule of the shared player is the one applied here.
        """
        internal = self.comment()
        for_client = self.comment(for_client=True)
        from_guest = self.comment(person=self.guest())

        shared = playlist_sharing_service.get_shared_task_comments(
            self.task.id
        )
        self.assertEqual(
            {comment["id"] for comment in shared},
            {str(for_client.id), str(from_guest.id)},
        )
        self.assertNotIn(
            str(internal.id), [comment["id"] for comment in shared]
        )

    def test_a_guest_author_is_flagged_as_one(self):
        """
        The player styles guest authors apart from studio members, and
        the person payload of a comment carries no is_guest of its own.
        """
        self.comment(person=self.guest())
        self.comment(for_client=True)

        by_author = {
            comment["person"]["id"]: comment["person"]["is_guest"]
            for comment in playlist_sharing_service.get_shared_task_comments(
                self.task.id
            )
        }
        self.assertEqual(
            by_author,
            {
                str(Person.get_by(email="reviewer@guest.kitsu").id): True,
                str(self.person.id): False,
            },
        )

    def share_a_comment_attachment(self, **comment_fields):
        """
        Position the playlist on the task, comment on it, and attach a file.
        Returns the share token and the attachment id.
        """
        preview = self.preview()
        self.position(
            {
                "entity_id": str(self.asset.id),
                "preview_file_id": str(preview.id),
            }
        )
        attachment = AttachmentFile.create(
            name="note.png",
            size=3,
            extension="png",
            mimetype="image/png",
            comment_id=self.comment(**comment_fields).id,
        )
        return self.share(), str(attachment.id)

    def download(self, token, attachment_id):
        # comments_service is imported inside the function, so the patch
        # lands on the source module rather than on a local alias.
        with patch.object(
            comments_service,
            "get_attachment_file_path",
            return_value="/tmp/note.png",
        ), patch("flask.send_file") as send_file:
            playlist_sharing_service.download_shared_attachment(
                token, attachment_id, "note.png"
            )
        return send_file

    def test_download_shared_attachment(self):
        token, attachment_id = self.share_a_comment_attachment(for_client=True)
        send_file = self.download(token, attachment_id)
        # A png is safe to render in the browser, so it is served inline.
        self.assertFalse(send_file.call_args.kwargs["as_attachment"])

    def test_download_forces_an_unsafe_mimetype(self):
        """
        The share link is unauthenticated and the mimetype comes from the
        uploader, so anything the browser would execute in Kitsu's origin
        is served as a download.
        """
        token, attachment_id = self.share_a_comment_attachment(for_client=True)
        AttachmentFile.get(attachment_id).update({"mimetype": "text/html"})
        send_file = self.download(token, attachment_id)
        self.assertTrue(send_file.call_args.kwargs["as_attachment"])

    def test_download_refused_on_a_comment_hidden_from_the_client(self):
        token, attachment_id = self.share_a_comment_attachment(
            for_client=False
        )
        self.assertRaises(
            GuestCommentNotFound,
            playlist_sharing_service.download_shared_attachment,
            token,
            attachment_id,
            "note.png",
        )

    def test_download_refused_on_a_task_outside_the_playlist(self):
        token, attachment_id = self.share_a_comment_attachment(for_client=True)
        self.position()
        self.assertRaises(
            GuestCommentNotFound,
            playlist_sharing_service.download_shared_attachment,
            token,
            attachment_id,
            "note.png",
        )
