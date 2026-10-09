import datetime

from unittest import mock

from sqlalchemy import text


from zou.app import db
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.time_spent import TimeSpent

from zou.app.services import (
    deletion_service,
    news_service,
)
from zou.app.utils import date_helpers
from zou.app.exceptions import (
    CommentNotFoundException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
)
from tests.services.cases import DeletionTestCase, FilesTestCase

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class RemoveCommentTestCase(DeletionTestCase):
    def test_remove_comment(self):
        self.generate_fixture_comment()
        comment_id = self.comment["id"]

        result = deletion_service.remove_comment(comment_id)

        self.assertEqual(result["id"], comment_id)
        self.assertIsNone(Comment.get(comment_id))

    def test_remove_comment_with_deleted_task(self):
        # The task is read to refresh its status; it may already be gone.
        self.generate_fixture_comment()
        comment_id = self.comment["id"]

        with mock.patch.object(Task, "get", return_value=None):
            result = deletion_service.remove_comment(comment_id)

        self.assertEqual(result["id"], comment_id)
        self.assertIsNone(Comment.get(comment_id))

    def test_remove_comment_takes_its_previews_with_it(self):
        self.generate_fixture_comment()
        self.generate_fixture_preview_file()
        comment = Comment.get(self.comment["id"])
        comment.previews.append(self.preview_file)
        comment.save()

        deletion_service.remove_comment(self.comment["id"])

        self.assertIsNone(PreviewFile.get(self.preview_file.id))

    def test_remove_comment_drops_its_news_from_cache_and_listeners(self):
        """
        The single-news route reads through a memoized get_news, and the
        news feed of the clients only learns of a removal through
        news:delete.
        """
        self.generate_fixture_comment()
        news = news_service.create_news_for_task_and_comment(
            self.task.serialize(), self.comment
        )
        project_id = str(self.project.id)
        self.assertEqual(
            len(news_service.get_news(project_id, news["id"])["data"]), 1
        )
        captured = self.capture_events("news:delete")

        deletion_service.remove_comment(self.comment["id"])

        self.assertEqual(
            news_service.get_news(project_id, news["id"])["data"], []
        )
        self.assertEqual(
            [event["news_id"] for event in captured], [news["id"]]
        )

    def test_remove_comment_not_found(self):
        with self.assertRaises(CommentNotFoundException):
            deletion_service.remove_comment(UNKNOWN)


class RemoveTaskTestCase(DeletionTestCase):
    def test_remove_task(self):
        task_id = str(self.task.id)

        result = deletion_service.remove_task(task_id)

        self.assertEqual(result["id"], task_id)
        self.assertIsNone(Task.get(task_id))

    def test_remove_task_force(self):
        # A comment and a time spent are what a plain removal refuses on.
        self.generate_fixture_comment()
        TimeSpent.create(
            person_id=self.person.id,
            task_id=self.task.id,
            date=datetime.date(2017, 9, 23),
            duration=3600,
        )
        task_id = str(self.task.id)

        result = deletion_service.remove_task(task_id, force=True)

        self.assertEqual(result["id"], task_id)
        self.assertIsNone(Task.get(task_id))

    def test_remove_task_force_announces_its_news(self):
        self.generate_fixture_comment()
        news = news_service.create_news_for_task_and_comment(
            self.task.serialize(), self.comment
        )
        captured = self.capture_events("news:delete")

        deletion_service.remove_task(str(self.task.id), force=True)

        self.assertEqual(
            [event["news_id"] for event in captured], [news["id"]]
        )

    def test_remove_tasks_for_project_and_task_type(self):
        """
        Scoped twice over: the other task type of the same production and
        the same task type of another production both survive.
        """
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        other_task_type = str(self.generate_fixture_task_standard().id)
        other_production = str(self.shot_task.id)
        removed = [
            str(self.task.id),
            str(self.generate_fixture_task(name="second task").id),
        ]

        deletion_service.remove_tasks_for_project_and_task_type(
            self.project.id, self.task_type.id
        )

        for task_id in removed:
            self.assertIsNone(Task.get(task_id))
        self.assertIsNotNone(Task.get(other_task_type))
        self.assertIsNotNone(Task.get(other_production))

    def test_remove_tasks(self):
        task_id = str(self.task.id)

        result = deletion_service.remove_tasks(str(self.project.id), [task_id])

        self.assertEqual(result, [task_id])
        self.assertIsNone(Task.get(task_id))

    def test_remove_tasks_invalid_ids(self):
        # A malformed id is skipped rather than raised on: the route takes
        # a list and the rest of it still has to go.
        result = deletion_service.remove_tasks(
            str(self.project.id), ["not-a-uuid"]
        )

        self.assertEqual(result, [])

    def generate_unassigned_tasks(self):
        """
        Two animation tasks with no assignee, so that a plain DELETE can
        take either of them.
        """
        return [
            str(
                Task.create(
                    name=name,
                    project_id=self.project.id,
                    task_type_id=self.task_type_animation.id,
                    task_status_id=self.task_status.id,
                    entity_id=self.asset.id,
                ).id
            )
            for name in ["Blocking", "Polish"]
        ]

    def delete_the_other_task_first(self, task_ids):
        """
        Make each removal first delete the other given task straight on the
        table, out of sight of the session, as a concurrent request does.
        """
        remove_task = deletion_service.remove_task

        def remove_task_after_the_other(task_id, force=False):
            for other_id in task_ids:
                if other_id != str(task_id):
                    db.session.execute(
                        text("DELETE FROM task WHERE id = :task_id"),
                        {"task_id": other_id},
                    )
            db.session.commit()
            return remove_task(task_id, force=force)

        return mock.patch.object(
            deletion_service,
            "remove_task",
            side_effect=remove_task_after_the_other,
        )

    def test_remove_tasks_skips_a_task_deleted_meanwhile(self):
        # Regression: every removal commits, which expired the instances
        # left to walk, and reading the id of the deleted one raised
        # ObjectDeletedError.
        task_ids = self.generate_unassigned_tasks()

        with self.delete_the_other_task_first(task_ids):
            result = deletion_service.remove_tasks(
                str(self.project.id), task_ids
            )

        self.assertEqual(result, task_ids)
        for task_id in task_ids:
            self.assertIsNone(Task.get(task_id))

    def test_remove_tasks_for_task_type_skips_one_deleted_meanwhile(self):
        task_ids = self.generate_unassigned_tasks()

        with self.delete_the_other_task_first(task_ids):
            deletion_service.remove_tasks_for_project_and_task_type(
                str(self.project.id), str(self.task_type_animation.id)
            )

        for task_id in task_ids:
            self.assertIsNone(Task.get(task_id))


class RemovePreviewFileTestCase(DeletionTestCase):
    def test_remove_preview_file_by_id(self):
        self.generate_fixture_preview_file()
        preview_id = str(self.preview_file.id)

        result = deletion_service.remove_preview_file_by_id(preview_id)

        self.assertEqual(result["id"], preview_id)
        self.assertIsNone(PreviewFile.get(preview_id))

    def test_clear_movie_files_removes_the_original_frame(self):
        # The movie pipeline stores the first frame as the "original"
        # picture, which used to be left behind in the store.
        with mock.patch.object(
            deletion_service.file_store, "remove_files"
        ) as remove_files:
            deletion_service.clear_movie_files("some-id")
        remove_files.assert_called_once()
        removed = set(remove_files.call_args.args[0])
        self.assertIn(("pictures", "original", "some-id"), removed)
        self.assertIn(("pictures", "tiles", "some-id"), removed)
        self.assertIn(("movies", "lowdef", "some-id"), removed)

    def test_remove_preview_file_keeps_files_when_db_delete_fails(self):
        self.generate_fixture_preview_file()

        with mock.patch.object(
            deletion_service, "clear_movie_files"
        ) as clear_files, mock.patch.object(
            PreviewFile, "delete", side_effect=RuntimeError
        ):
            with self.assertRaises(RuntimeError):
                deletion_service.remove_preview_file_by_id(
                    str(self.preview_file.id), force=True
                )

        clear_files.assert_not_called()

    def test_remove_preview_file_by_id_not_found(self):
        with self.assertRaises(PreviewFileNotFoundException):
            deletion_service.remove_preview_file_by_id(UNKNOWN)

    def test_remove_preview_background_file_not_found(self):
        with self.assertRaises(PreviewBackgroundFileNotFoundException):
            deletion_service.remove_preview_background_file_by_id(UNKNOWN)


class RemoveOldRowsTestCase(DeletionTestCase):
    """
    The nightly housekeeping: three log tables trimmed to a window. Each
    case holds a row on either side of it, since a removal that takes
    everything and one that takes nothing both look right with only one.
    """

    def age(self, row, days):
        """
        Move a row back in time and hand back its id: the bulk delete
        leaves the instance stale, and reading an attribute off it
        afterwards raises rather than answering.
        """
        row.update(
            {
                "created_at": date_helpers.get_utc_now_datetime()
                - datetime.timedelta(days=days)
            }
        )
        return str(row.id)

    def a_notification(self, author_id):
        return Notification.create(
            type="comment",
            person_id=self.person.id,
            author_id=author_id,
            task_id=self.task.id,
        )

    def test_remove_old_events(self):
        old = self.age(ApiEvent.create(name="old:event"), 100)
        recent = self.age(ApiEvent.create(name="recent:event"), 80)

        deletion_service.remove_old_events()

        self.assertIsNone(ApiEvent.get(old))
        self.assertIsNotNone(ApiEvent.get(recent))

    def test_remove_old_events_takes_its_window(self):
        row = self.age(ApiEvent.create(name="old:event"), 10)

        deletion_service.remove_old_events(days_old=30)
        self.assertIsNotNone(ApiEvent.get(row))

        deletion_service.remove_old_events(days_old=5)
        self.assertIsNone(ApiEvent.get(row))

    def test_remove_old_login_logs(self):
        old = self.age(LoginLog.create(person_id=self.person.id), 100)
        recent = self.age(LoginLog.create(person_id=self.person.id), 80)

        deletion_service.remove_old_login_logs()

        self.assertIsNone(LoginLog.get(old))
        self.assertIsNotNone(LoginLog.get(recent))

    def test_remove_old_notifications(self):
        old = self.age(self.a_notification(self.person.id), 100)
        recent = self.age(self.a_notification(self.user["id"]), 80)

        deletion_service.remove_old_notifications()

        self.assertIsNone(Notification.get(old))
        self.assertIsNotNone(Notification.get(recent))


class RemoveProjectTestCase(DeletionTestCase):
    def test_remove_output_files_for_entity(self):
        """
        Scoped to the entity it is given, and it breaks the preview files
        pointing at what it removes: the foreign key would refuse
        otherwise, which is the whole reason this runs before a deletion.
        """
        self.generate_fixture_output_type()
        self.generate_fixture_department()
        self.generate_fixture_software()
        self.generate_fixture_working_file()
        output_file = self.generate_fixture_output_file()
        output_file_id = str(output_file.id)
        preview_file = self.generate_fixture_preview_file()
        preview_file.update({"source_file_id": output_file.id})
        # A second entity keeps its own, so a removal walking the whole
        # table cannot pass.
        elsewhere = self.generate_fixture_shot()
        other_task = self.generate_fixture_task(
            name="other", entity_id=elsewhere.id
        )
        other_output_id = str(
            self.generate_fixture_output_file(task=other_task).id
        )

        result = deletion_service.remove_output_files_for_entity(
            str(self.asset.id)
        )

        self.assertEqual([str(row.id) for row in result], [output_file_id])
        self.assertIsNone(OutputFile.get(output_file_id))
        self.assertIsNotNone(OutputFile.get(other_output_id))
        self.assertIsNone(PreviewFile.get(preview_file.id).source_file_id)


class PreviewFileRowRemovalTestCase(FilesTestCase):
    def test_a_removed_preview_is_announced(self):
        self.generate_fixture_preview_file()
        captured = self.capture_events("preview-file:delete")
        deletion_service.remove_preview_file_row(self.preview_file.id)
        self.assertEqual(len(captured), 1)
