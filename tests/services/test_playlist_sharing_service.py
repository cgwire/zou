from tests.base import ApiDBTestCase

from zou.app.models.playlist import Playlist as PlaylistModel
from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task

from zou.app.services import playlist_sharing_service


class PlaylistSharingServiceTestCase(ApiDBTestCase):
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
        self.playlist = self.generate_fixture_playlist("Test Playlist")

    def share(self):
        """
        Share the playlist and return the token to check membership against.
        """
        link = playlist_sharing_service.create_share_link(
            self.playlist["id"], self.person.id
        )
        return link["token"]

    def test_membership_same_entity_in_several_shots(self):
        """
        A playlist may list the same entity several times, each shot
        positioned on a different task type and a different revision (e.g.
        one task pinned to revision 2 and another to revision 1). Every
        positioned preview must pass the shared-playlist membership check,
        not only the last shot's. Before the fix the check collapsed the
        shots into a single entity -> preview_file_id mapping (regression
        from 54ec061ce): only the last shot's preview, and any preview
        sharing its revision number, was served — so the revision 2 preview
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
        first_preview = PreviewFile.create(
            name="first.png",
            revision=2,
            extension="png",
            task_id=first_task.id,
            person_id=self.person.id,
        )
        second_preview = PreviewFile.create(
            name="second.png",
            revision=1,
            extension="png",
            task_id=second_task.id,
            person_id=self.person.id,
        )
        PlaylistModel.get(self.playlist["id"]).update(
            {
                "shots": [
                    {
                        "entity_id": str(self.asset.id),
                        "preview_file_id": str(first_preview.id),
                    },
                    {
                        "entity_id": str(self.asset.id),
                        "preview_file_id": str(second_preview.id),
                    },
                ]
            }
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
        sibling = PreviewFile.create(
            name="first-pos2.png",
            revision=first_preview.revision,
            position=first_preview.position + 1,
            extension="png",
            task_id=first_task.id,
            person_id=self.person.id,
        )
        self.assertTrue(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(sibling.id)
            )
        )

        # A different revision of a positioned task stays rejected.
        other_revision = PreviewFile.create(
            name="first-rev2.png",
            revision=first_preview.revision + 1,
            extension="png",
            task_id=first_task.id,
            person_id=self.person.id,
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
        cross_task_collision = PreviewFile.create(
            name="second-rev2.png",
            revision=first_preview.revision,  # 2: same number as first_preview
            extension="png",
            task_id=second_task.id,  # but a different (also positioned) task
            person_id=self.person.id,
        )
        self.assertFalse(
            playlist_sharing_service.is_preview_file_in_shared_playlist(
                token, str(cross_task_collision.id)
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
        positioned = PreviewFile.create(
            name="positioned.png",
            revision=1,
            extension="png",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        # Another, non-positioned preview of the same entity, on a different
        # revision, so it is not a member.
        other = PreviewFile.create(
            name="other.png",
            revision=2,
            extension="png",
            task_id=self.task.id,
            person_id=self.person.id,
        )
        PlaylistModel.get(self.playlist["id"]).update(
            {
                "shots": [
                    {
                        "entity_id": str(self.asset.id),
                        "preview_file_id": str(positioned.id),
                    }
                ]
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
