from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.notification import Notification
from zou.app.models.news import News
from zou.app.models.preview_file import PreviewFile
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog

from zou.app.services import (
    comments_service,
    deletion_service,
    tasks_service,
)
from zou.app.services.exception import (
    CommentNotFoundException,
    PreviewFileNotFoundException,
)


class DeletionServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(DeletionServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()

    def test_remove_comment(self):
        self.generate_fixture_comment()
        comment_id = self.comment["id"]
        result = deletion_service.remove_comment(comment_id)
        self.assertEqual(result["id"], comment_id)

    def test_remove_comment_not_found(self):
        with self.assertRaises(CommentNotFoundException):
            deletion_service.remove_comment(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_remove_comment_with_preview(self):
        self.generate_fixture_comment()
        self.generate_fixture_preview_file()
        comment = Comment.get(self.comment["id"])
        comment.previews.append(self.preview_file)
        comment.save()
        comment_id = self.comment["id"]
        result = deletion_service.remove_comment(comment_id)
        self.assertEqual(result["id"], comment_id)
        self.assertIsNone(PreviewFile.get(self.preview_file.id))

    def test_remove_task(self):
        task_id = str(self.task.id)
        result = deletion_service.remove_task(task_id)
        self.assertEqual(result["id"], task_id)
        self.assertIsNone(Task.get(task_id))

    def test_remove_task_force(self):
        self.generate_fixture_comment()
        task_id = str(self.task.id)
        result = deletion_service.remove_task(task_id, force=True)
        self.assertEqual(result["id"], task_id)
        self.assertIsNone(Task.get(task_id))

    def test_remove_tasks(self):
        task_id = str(self.task.id)
        result = deletion_service.remove_tasks(
            str(self.project.id), [task_id]
        )
        self.assertIn(task_id, result)
        self.assertIsNone(Task.get(task_id))

    def test_remove_tasks_invalid_ids(self):
        result = deletion_service.remove_tasks(
            str(self.project.id), ["not-a-uuid"]
        )
        self.assertEqual(result, [])

    def test_remove_preview_file_by_id(self):
        self.generate_fixture_preview_file()
        preview_id = str(self.preview_file.id)
        result = deletion_service.remove_preview_file_by_id(preview_id)
        self.assertEqual(result["id"], preview_id)
        self.assertIsNone(PreviewFile.get(preview_id))

    def test_remove_preview_file_by_id_not_found(self):
        with self.assertRaises(PreviewFileNotFoundException):
            deletion_service.remove_preview_file_by_id(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_remove_old_events(self):
        ApiEvent.create(
            name="test:event",
            user_id=str(self.person.id),
        )
        count_before = ApiEvent.query.count()
        self.assertGreater(count_before, 0)
        # Events created now should not be removed with default 90 days
        deletion_service.remove_old_events()
        count_after = ApiEvent.query.count()
        self.assertEqual(count_before, count_after)

    def test_remove_old_login_logs(self):
        LoginLog.create(person_id=self.person.id)
        count_before = LoginLog.query.count()
        self.assertGreater(count_before, 0)
        deletion_service.remove_old_login_logs()
        count_after = LoginLog.query.count()
        self.assertEqual(count_before, count_after)

    def test_remove_old_notifications(self):
        deletion_service.remove_old_notifications()
        count = Notification.query.count()
        self.assertEqual(count, 0)

    def test_remove_output_files_for_entity(self):
        result = deletion_service.remove_output_files_for_entity(
            str(self.asset.id)
        )
        self.assertEqual(result, [])
