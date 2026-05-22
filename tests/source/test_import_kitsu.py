from tests.base import ApiDBTestCase

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.build_job import BuildJob
from zou.app.models.comment import Comment
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.milestone import Milestone
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.playlist import Playlist
from zou.app.models.preview_file import PreviewFile
from zou.app.models.schedule_item import ScheduleItem
from zou.app.models.subscription import Subscription
from zou.app.models.time_spent import TimeSpent
from zou.app.utils import fields


class ImportKitsuRoutesTestCase(ApiDBTestCase):
    """
    Exercise the /import/kitsu/* routes — they back the sync-push workflow
    (CLI sync-push posts serialized local rows to these routes on the
    target instance).
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()
        self.task_id = str(self.task.id)
        self.project_id = str(self.project.id)

    def _post_kitsu(self, path, payload, code=200):
        return self.post(path, payload, code=code)

    def test_import_metadata_descriptors(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "project_id": self.project_id,
                "name": "Vendor",
                "field_name": "vendor",
                "data_type": "string",
                "entity_type": "Asset",
                "choices": [],
                "for_client": False,
                "departments": [str(self.department.id)],
            }
        ]
        self._post_kitsu("/import/kitsu/metadata-descriptors", payload)
        self.assertIsNotNone(MetadataDescriptor.get(new_id))

        # Idempotent: same payload again is an update path.
        self._post_kitsu("/import/kitsu/metadata-descriptors", payload)

    def test_import_milestones(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "project_id": self.project_id,
                "task_type_id": str(self.task_type.id),
                "name": "Pitch",
                "date": "2026-06-01",
            }
        ]
        self._post_kitsu("/import/kitsu/milestones", payload)
        self.assertIsNotNone(Milestone.get(new_id))
        self._post_kitsu("/import/kitsu/milestones", payload)

    def test_import_schedule_items(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "project_id": self.project_id,
                "task_type_id": str(self.task_type.id),
                "object_id": str(self.asset.id),
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
            }
        ]
        self._post_kitsu("/import/kitsu/schedule-items", payload)
        self.assertIsNotNone(ScheduleItem.get(new_id))
        self._post_kitsu("/import/kitsu/schedule-items", payload)

    def test_import_playlists(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "project_id": self.project_id,
                "name": "Daily",
                "for_entity": "shot",
                "for_client": False,
                "is_for_all": False,
                "shots": [],
                "build_jobs": [],
            }
        ]
        self._post_kitsu("/import/kitsu/playlists", payload)
        self.assertIsNotNone(Playlist.get(new_id))
        self._post_kitsu("/import/kitsu/playlists", payload)

    def test_import_subscriptions(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "task_id": self.task_id,
                "entity_id": str(self.asset.id),
                "task_type_id": str(self.task_type.id),
                "person_id": self.user["id"],
            }
        ]
        self._post_kitsu("/import/kitsu/subscriptions", payload)
        self.assertIsNotNone(Subscription.get(new_id))
        self._post_kitsu("/import/kitsu/subscriptions", payload)

    def test_import_notifications(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "notification_type": "comment",
                "task_id": self.task_id,
                "comment_id": self.comment["id"],
                "person_id": self.user["id"],
                "author_id": str(self.person.id),
                "read": False,
                "change": False,
            }
        ]
        self._post_kitsu("/import/kitsu/notifications", payload)
        self.assertIsNotNone(Notification.get(new_id))
        self._post_kitsu("/import/kitsu/notifications", payload)

    def test_import_time_spents(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "task_id": self.task_id,
                "person_id": str(self.person.id),
                "date": "2026-05-20",
                "duration": 480,
            }
        ]
        self._post_kitsu("/import/kitsu/time-spents", payload)
        self.assertIsNotNone(TimeSpent.get(new_id))
        self._post_kitsu("/import/kitsu/time-spents", payload)

    def test_import_news(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "task_id": self.task_id,
                "comment_id": self.comment["id"],
                "preview_file_id": None,
                "author_id": str(self.person.id),
                "change": False,
                "created_at": "2026-05-20T10:00:00",
            }
        ]
        self._post_kitsu("/import/kitsu/news", payload)
        self.assertIsNotNone(News.get(new_id))
        self._post_kitsu("/import/kitsu/news", payload)

    def test_import_preview_files(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "task_id": self.task_id,
                "name": "v001",
                "revision": 1,
                "position": 1,
                "extension": "mp4",
                "status": "ready",
                "validation_status": "neutral",
            }
        ]
        self._post_kitsu("/import/kitsu/preview-files", payload)
        self.assertIsNotNone(PreviewFile.get(new_id))
        self._post_kitsu("/import/kitsu/preview-files", payload)

    def test_import_build_jobs(self):
        playlist = Playlist.create(
            name="Build job test",
            project_id=self.project.id,
            for_entity="shot",
            shots=[],
        )
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "playlist_id": str(playlist.id),
                "status": "succeeded",
                "job_type": "movie",
            }
        ]
        self._post_kitsu("/import/kitsu/build-jobs", payload)
        self.assertIsNotNone(BuildJob.get(new_id))
        self._post_kitsu("/import/kitsu/build-jobs", payload)

    def test_import_attachment_files(self):
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "name": "bug.png",
                "size": 42,
                "extension": "png",
                "mimetype": "image/png",
                "comment_id": self.comment["id"],
            }
        ]
        self._post_kitsu("/import/kitsu/attachment-files", payload)
        self.assertIsNotNone(AttachmentFile.get(new_id))
        self._post_kitsu("/import/kitsu/attachment-files", payload)

    def test_import_comments_fixed_model(self):
        """
        Regression: ImportKitsuCommentsResource used to be wired to Entity
        instead of Comment. POSTing a comment payload now actually creates
        a Comment row.
        """
        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "object_id": self.task_id,
                "object_type": "Task",
                "text": "Imported comment",
                "person_id": str(self.person.id),
                "task_status_id": str(self.task_status.id),
            }
        ]
        self._post_kitsu("/import/kitsu/comments", payload)
        self.assertIsNotNone(Comment.get(new_id))

    def test_non_admin_is_denied(self):
        """
        check_access falls back to has_admin_permissions on every
        /import/kitsu/* route: a non-admin caller can POST but no row
        gets created.
        """
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()

        new_id = str(fields.gen_uuid())
        payload = [
            {
                "id": new_id,
                "project_id": self.project_id,
                "task_type_id": str(self.task_type.id),
                "name": "Should not import",
                "date": "2026-06-01",
            }
        ]
        response = self._post_kitsu("/import/kitsu/milestones", payload)
        self.assertEqual(response, [])
        self.assertIsNone(Milestone.get(new_id))
