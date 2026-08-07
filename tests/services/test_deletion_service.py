import datetime

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.task import Task
from zou.app.models.notification import Notification
from zou.app.models.output_file import OutputFile
from zou.app.models.preview_file import PreviewFile
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.project import Project
from zou.app.models.time_spent import TimeSpent

from zou.app.services import deletion_service, shots_service
from zou.app.utils import date_helpers
from zou.app.services.exception import (
    CommentNotFoundException,
    EpisodeNotFoundException,
    ModelWithRelationsDeletionException,
    PreviewBackgroundFileNotFoundException,
    PreviewFileNotFoundException,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class DeletionTestCase(ApiDBTestCase):
    """
    Base fixture set: one production with an asset carrying a task.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_task_type()
        self.generate_fixture_task()


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


class RemovePreviewFileTestCase(DeletionTestCase):
    def test_remove_preview_file_by_id(self):
        self.generate_fixture_preview_file()
        preview_id = str(self.preview_file.id)

        result = deletion_service.remove_preview_file_by_id(preview_id)

        self.assertEqual(result["id"], preview_id)
        self.assertIsNone(PreviewFile.get(preview_id))

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


class RemoveEpisodeTestCase(DeletionTestCase):
    """
    An episode is the top of a tree: sequences, shots, assets and their
    tasks hang off it, and it only goes when the tree does.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        self.episode_id = str(self.episode.id)

    def test_remove_episode_refuses_what_is_still_linked(self):
        # Nothing is read back afterwards: the refusal rolls the session
        # back, and the fixtures of this test are uncommitted work that
        # goes with it. In production each request owns its transaction.
        with self.assertRaises(ModelWithRelationsDeletionException):
            deletion_service.remove_episode(self.episode_id)

    def test_remove_episode_force_takes_the_tree_with_it(self):
        sequence_id = str(self.sequence.id)
        shot_id = str(self.shot.id)
        task_id = str(self.shot_task.id)

        result = deletion_service.remove_episode(self.episode_id, force=True)

        self.assertEqual(result["id"], self.episode_id)
        for entity_id in [self.episode_id, sequence_id, shot_id]:
            self.assertIsNone(Entity.get(entity_id))
        self.assertIsNone(Task.get(task_id))

    def test_remove_episode_announces_it(self):
        captured = self.capture_events("episode:delete")

        deletion_service.remove_episode(self.episode_id, force=True)

        self.assertEqual(
            [(event["episode_id"], event["project_id"]) for event in captured],
            [(self.episode_id, str(self.project.id))],
        )

    def test_remove_episode_not_found(self):
        with self.assertRaises(EpisodeNotFoundException):
            deletion_service.remove_episode(UNKNOWN)

    def test_removing_an_episode_leaves_the_other_one_alone(self):
        here = self.episode_id
        elsewhere = self.generate_fixture_episode("E02")
        other_sequence = self.generate_fixture_sequence(
            "S02", episode_id=elsewhere.id
        )

        deletion_service.remove_episode(here, force=True)

        self.assertIsNotNone(Entity.get(str(elsewhere.id)))
        self.assertIsNotNone(Entity.get(str(other_sequence.id)))


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

    def test_remove_project_with_production_schedule_version(self):
        # Regression: deleting a project that had a production schedule
        # version failed on the FK constraint because the version (and its
        # task links + self-reference) were never cleaned up.
        project_id = str(self.project.id)
        version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        derived = ProductionScheduleVersion.create(
            name="v2",
            project_id=self.project.id,
            production_schedule_from=version.id,
        )
        ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=version.id,
            task_id=self.task.id,
        )
        version_id = str(version.id)
        derived_id = str(derived.id)

        deletion_service.remove_project(project_id)

        self.assertIsNone(Project.get(project_id))
        self.assertIsNone(ProductionScheduleVersion.get(version_id))
        self.assertIsNone(ProductionScheduleVersion.get(derived_id))

    def test_remove_project_leaves_the_other_productions_alone(self):
        """
        remove_project walks a dozen tables, each scoped to the production
        it was given. One row of every shape lives in a second production
        here, and all of them must survive.
        """
        self.generate_fixture_project_standard()
        other_asset = self.generate_fixture_asset(
            "Car", project_id=self.project_standard.id
        )
        other_task = self.generate_fixture_task(
            name="other", entity_id=other_asset.id
        )
        other_task.update({"project_id": self.project_standard.id})
        other_preview = PreviewFile.create(
            name="other.png",
            revision=1,
            extension="png",
            task_id=other_task.id,
            person_id=self.person.id,
        )
        other_version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project_standard.id
        )
        # The version rows are deleted by project id, but the task links
        # and the self references are broken by the id list built above
        # them, which is scoped separately.
        other_link = ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=other_version.id,
            task_id=other_task.id,
        )
        self.generate_fixture_output_type()
        other_output = self.generate_fixture_output_file(task=other_task)
        survivors = [
            (Task, str(other_task.id)),
            (PreviewFile, str(other_preview.id)),
            (ProductionScheduleVersion, str(other_version.id)),
            (ProductionScheduleVersionTaskLink, str(other_link.id)),
            (OutputFile, str(other_output.id)),
        ]

        deletion_service.remove_project(str(self.project.id))

        for model, row_id in survivors:
            self.assertIsNotNone(model.get(row_id), model.__name__)
        self.assertIsNotNone(Project.get(str(self.project_standard.id)))
