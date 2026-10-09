import datetime

from unittest import mock

from sqlalchemy import text


from zou.app import db
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.task import Task
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.time_spent import TimeSpent

from zou.app.services import (
    deletion_service,
    entities_service,
    news_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import date_helpers, events
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

        def remove_task_after_the_other(
            task_id, force=False, restore_main=True
        ):
            for other_id in task_ids:
                if other_id != str(task_id):
                    db.session.execute(
                        text("DELETE FROM task WHERE id = :task_id"),
                        {"task_id": other_id},
                    )
            db.session.commit()
            return remove_task(task_id, force=force, restore_main=restore_main)

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


class RestoreMainPreviewTestCase(DeletionTestCase):
    """
    What an upload made current goes back to the previous main preview when
    the preview is removed, and the clients hear of it.
    """

    def generate_preview(
        self,
        revision,
        day,
        name="main",
        position=1,
        status="ready",
        extension="mp4",
    ):
        preview_file = self.generate_fixture_preview_file(
            revision=revision, name=name, position=position, status=status
        )
        preview_file.update(
            {
                "created_at": datetime.datetime(2026, 1, day),
                "extension": extension,
            }
        )
        return preview_file

    def show(self, preview_file):
        self.task.update({"last_preview_file_id": preview_file.id})
        Entity.get(self.asset.id).update({"preview_file_id": preview_file.id})

    def automate_previews(self):
        projects_service.update_project(
            str(self.project.id), {"is_set_preview_automated": True}
        )

    def get_task_main(self):
        return Task.get(self.task.id).last_preview_file_id

    def get_entity_main(self):
        return Entity.get(self.asset.id).preview_file_id

    def read_through_caches(self):
        return (
            tasks_service.get_task(self.task.id)["last_preview_file_id"],
            entities_service.get_entity(self.asset.id)["preview_file_id"],
        )

    def capture_in_order(self, *names):
        """
        Collect given events in one list, as (name, payload) pairs in the
        order they come, see capture_events.
        """
        captured = []

        class Handler:
            def __init__(self, name):
                self.name = name

            def handle_event(self, data=None):
                captured.append((self.name, data or {}))

        events.unregister_all()
        for name in names:
            events.register(name, f"{name}_test_handler", Handler(name))
        return captured

    def generate_tasks_removed_together(self):
        """
        Two tasks of one type: the entity shows the preview of the first
        and the second holds the next newest one. A task of another type
        keeps an older one, which the entity must end up with. Return the
        ids of the two tasks and that preview.
        """
        self.automate_previews()
        self.generate_fixture_task(
            name="Kept", task_type_id=self.task_type_modeling.id
        )
        kept = self.generate_preview(1, 1)
        first_task = self.generate_fixture_task(name="First")
        shown = self.generate_preview(1, 3)
        second_task = self.generate_fixture_task(name="Second")
        self.generate_preview(1, 2)
        Entity.get(self.asset.id).update({"preview_file_id": shown.id})
        return [str(first_task.id), str(second_task.id)], kept

    def test_remove_main_preview_skips_the_extra_file_of_its_revision(self):
        # The newest remaining preview is the extra file, which an upload
        # never makes current: the task kept the removed preview and the
        # entity was left without a thumbnail, both in silence.
        self.automate_previews()
        previous = self.generate_preview(1, 1)
        main = self.generate_preview(2, 2)
        self.generate_preview(2, 3, name="extra", position=2)
        self.show(main)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_preview_file(main)

        self.assertEqual(self.get_task_main(), previous.id)
        self.assertEqual(self.get_entity_main(), previous.id)
        self.assertEqual(
            [
                (event["entity_id"], event["preview_file_id"])
                for event in captured
            ],
            [(str(self.asset.id), str(previous.id))],
        )

    def test_remove_comment_announces_the_restored_preview_once(self):
        # Kitsu removes the whole comment when an extra file fails to
        # upload after the main one went through.
        self.automate_previews()
        previous = self.generate_preview(1, 1)
        main = self.generate_preview(2, 2)
        extra = self.generate_preview(2, 3, name="extra", position=2)
        self.show(main)
        self.generate_fixture_comment()
        comment = Comment.get(self.comment["id"])
        comment.previews.extend([main, extra])
        comment.save()
        self.read_through_caches()
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_comment(self.comment["id"])

        self.assertEqual(self.get_entity_main(), previous.id)
        self.assertEqual(
            [event["preview_file_id"] for event in captured],
            [str(previous.id)],
        )
        # The task reads of Kitsu and of the playlists go through the cache.
        self.assertEqual(
            self.read_through_caches(), (str(previous.id), str(previous.id))
        )

    def test_entity_goes_back_to_the_newest_main_preview_of_any_task(self):
        # Before the removed upload, the entity showed the other task's
        # preview, newer than the previous one of the same task.
        self.automate_previews()
        self.generate_preview(1, 1)
        main = self.generate_preview(2, 3)
        self.show(main)
        task = self.task
        self.generate_fixture_task(name="Second")
        other_task_preview = self.generate_preview(1, 2)
        self.task = task

        deletion_service.remove_preview_file(main)

        self.assertEqual(self.get_entity_main(), other_task_preview.id)

    def test_restore_skips_the_previews_without_a_thumbnail(self):
        # A generic file, a glb model for instance, is ready at once and
        # gets no thumbnail.
        self.automate_previews()
        previous = self.generate_preview(1, 1)
        self.generate_preview(2, 2, extension="glb")
        main = self.generate_preview(3, 3)
        self.show(main)

        deletion_service.remove_preview_file(main)

        self.assertEqual(self.get_task_main(), previous.id)
        self.assertEqual(self.get_entity_main(), previous.id)

    def test_restore_skips_the_previews_an_upload_never_made_current(self):
        self.automate_previews()
        previous = self.generate_preview(1, 1)
        self.generate_preview(2, 2, status="broken")
        main = self.generate_preview(3, 3)
        self.show(main)

        deletion_service.remove_preview_file(main)

        self.assertEqual(self.get_task_main(), previous.id)
        self.assertEqual(self.get_entity_main(), previous.id)

    def test_manual_thumbnail_is_removed_but_not_replaced(self):
        # Zou picks no thumbnail when the production sets them by hand; the
        # task still follows its previews.
        previous = self.generate_preview(1, 1)
        main = self.generate_preview(2, 2)
        self.show(main)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_preview_file(main)

        self.assertEqual(self.get_task_main(), previous.id)
        self.assertIsNone(self.get_entity_main())
        self.assertEqual(
            [
                (event["entity_id"], event["preview_file_id"])
                for event in captured
            ],
            [(str(self.asset.id), None)],
        )

    def test_removing_the_task_main_preview_announces_the_task(self):
        # Kitsu reloads a task on task:update: without one, the task cards
        # and lists of the other users kept asking for the removed preview.
        # An older revision is not what the task shows: nothing to announce.
        oldest = self.generate_preview(1, 1)
        previous = self.generate_preview(2, 2)
        main = self.generate_preview(3, 3)
        self.show(main)
        captured = self.capture_events("task:update")

        deletion_service.remove_preview_file(oldest)
        self.assertEqual(captured, [])

        deletion_service.remove_preview_file(main)
        self.assertEqual(self.get_task_main(), previous.id)
        self.assertEqual(
            [(event["task_id"], event["project_id"]) for event in captured],
            [(str(self.task.id), str(self.project.id))],
        )

    def test_removing_the_only_preview_announces_an_empty_thumbnail(self):
        self.automate_previews()
        main = self.generate_preview(1, 1)
        self.show(main)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_preview_file(main)

        self.assertIsNone(self.get_task_main())
        self.assertIsNone(self.get_entity_main())
        self.assertEqual(
            [event["preview_file_id"] for event in captured], [None]
        )

    def test_remove_task_announces_the_lost_thumbnail_once(self):
        # Every preview of the task goes: restoring one after the other
        # would announce previews about to be removed. The entity stays, so
        # it is told once, after the last one. The shown one is inserted
        # first, so that it is the first one removed.
        self.automate_previews()
        main = self.generate_preview(2, 2)
        self.generate_preview(1, 1)
        self.show(main)
        entities_service.get_entity(self.asset.id)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_task(str(self.task.id), force=True)

        self.assertIsNone(self.get_entity_main())
        self.assertIsNone(
            entities_service.get_entity(self.asset.id)["preview_file_id"]
        )
        self.assertEqual(
            [event["preview_file_id"] for event in captured], [None]
        )

    def test_remove_task_hands_the_thumbnail_to_another_task(self):
        # An upload on any task of the entity takes its thumbnail: once a
        # task goes, the newest main preview of the others does.
        self.automate_previews()
        removed_task = self.task
        other_task = self.generate_fixture_task(name="Other")
        self.task = removed_task
        other = self.generate_fixture_preview_file(task_id=other_task.id)
        main = self.generate_preview(2, 2)
        self.show(main)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_task(str(removed_task.id), force=True)

        self.assertEqual(self.get_entity_main(), other.id)
        self.assertEqual(
            [event["preview_file_id"] for event in captured], [str(other.id)]
        )

    def test_bulk_removal_restores_the_entity_once_after_the_last_task(self):
        # Restored after each task, the entity took the preview of the other
        # one, about to go, and announced it. With the other one removed
        # first, it was told before the batch was over: hence the order.
        task_ids, kept = self.generate_tasks_removed_together()
        captured = self.capture_in_order(
            "task:delete", "preview-file:set-main"
        )

        deletion_service.remove_tasks(str(self.project.id), task_ids)

        self.assertEqual(self.get_entity_main(), kept.id)
        self.assertEqual(
            [name for name, _ in captured],
            ["task:delete", "task:delete", "preview-file:set-main"],
        )
        self.assertEqual(captured[-1][1]["preview_file_id"], str(kept.id))

    def test_task_type_removal_restores_the_entity_once_at_the_end(self):
        # The same through the removal of every task of the type, which
        # takes the task of the base fixture too.
        _, kept = self.generate_tasks_removed_together()
        captured = self.capture_in_order(
            "task:delete", "preview-file:set-main"
        )

        deletion_service.remove_tasks_for_project_and_task_type(
            str(self.project.id), str(self.task_type.id)
        )

        self.assertEqual(self.get_entity_main(), kept.id)
        self.assertEqual(
            [name for name, _ in captured],
            ["task:delete"] * 3 + ["preview-file:set-main"],
        )
        self.assertEqual(captured[-1][1]["preview_file_id"], str(kept.id))

    def test_entity_removal_announces_no_preview(self):
        # The entity goes with its tasks: nothing is left to show.
        self.automate_previews()
        main = self.generate_preview(1, 1)
        self.show(main)
        captured = self.capture_events("preview-file:set-main")

        deletion_service.remove_tasks_for_entity(str(self.asset.id))

        self.assertEqual(captured, [])


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
