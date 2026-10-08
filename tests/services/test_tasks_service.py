# -*- coding: UTF-8 -*-
import datetime
import uuid

from unittest import mock

from sqlalchemy.orm.exc import StaleDataError

from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    comments_service,
    deletion_service,
    projects_service,
    tasks_service,
    task_types_service,
    time_spents_service,
    todos_service,
)

from zou.app.exceptions import (
    RevisionAlreadyExistsException,
    TaskNotFoundException,
)
from tests.services.cases import TaskTestCase


class TaskCreationTestCase(TaskTestCase):
    def test_create_task(self):
        shot = self.shot.serialize()
        task_type = self.task_type.serialize()
        status = task_types_service.get_default_task_status()

        task = tasks_service.create_task(task_type, shot)

        task = tasks_service.get_task(task["id"])
        self.assertEqual(task["entity_id"], shot["id"])
        self.assertEqual(task["task_type_id"], task_type["id"])
        self.assertEqual(task["project_id"], shot["project_id"])
        self.assertEqual(task["task_status_id"], status["id"])

    def test_create_tasks(self):
        shot = self.shot.serialize()
        shot_2 = self.generate_fixture_shot("S02").serialize()
        task_type = self.task_type.serialize()
        status = task_types_service.get_default_task_status()

        tasks = tasks_service.create_tasks(task_type, [shot, shot_2])

        self.assertEqual(len(tasks), 2)
        task = tasks_service.get_task(tasks[0]["id"])
        self.assertEqual(task["entity_id"], shot["id"])
        self.assertEqual(task["task_type_id"], task_type["id"])
        self.assertEqual(task["project_id"], shot["project_id"])
        self.assertEqual(task["task_status_id"], status["id"])


class TaskAssignationTestCase(TaskTestCase):
    def setUp(self):
        super().setUp()
        self.task.assignees = []
        self.task.save()

    def test_assign_task(self):
        tasks_service.assign_task(
            self.task.id, self.person.id, self.assigner.id
        )

        self.assertEqual(self.task.assignees[0].id, self.person.id)
        self.assertEqual(self.task.assigner_id, self.assigner.id)

    def test_assign_task_is_idempotent(self):
        tasks_service.assign_task(self.task.id, self.person.id)
        tasks_service.assign_task(self.task.id, self.person.id)

        self.assertEqual(len(self.task.assignees), 1)

    def test_assign_task_drops_the_task_cache(self):
        tasks_service.get_task(self.task_id, relations=True)

        tasks_service.assign_task(self.task_id, self.person_id)

        task = tasks_service.get_task(self.task_id, relations=True)
        self.assertEqual(task["assignees"], [self.person_id])

    def test_clear_assignation(self):
        tasks_service.assign_task(self.task.id, self.person.id)

        tasks_service.clear_assignation(self.task_id)

        task = tasks_service.get_task(self.task_id, relations=True)
        self.assertEqual(task["assignees"], [])

    def test_clear_assignation_swallows_stale_data_error(self):
        tasks_service.assign_task(self.task.id, self.person.id)
        task = tasks_service.get_task_raw(self.task_id)

        # A concurrent unassign makes the assignees flush delete a link that
        # is already gone, which SQLAlchemy reports as StaleDataError. clear_
        # assignation must treat that as already-cleared, not raise. (The real
        # rollback path can't be exercised here: the test harness keeps every
        # fixture in one uncommitted transaction, so any rollback wipes them.)
        with mock.patch.object(
            type(task), "update", side_effect=StaleDataError("stale link")
        ), mock.patch.object(tasks_service, "get_task_raw", return_value=task):
            result = tasks_service.clear_assignation(self.task_id)

        self.assertEqual(result["id"], self.task_id)


class TaskUpdateTestCase(TaskTestCase):
    def test_update_task_sets_the_end_date_on_feedback(self):
        wfa_status = self.generate_fixture_task_status_wfa()

        tasks_service.update_task(
            self.task.id, {"task_status_id": wfa_status["id"]}
        )

        self.assertEqual(str(self.task.task_status_id), wfa_status["id"])
        self.assertIsNotNone(self.task.end_date)
        self.assertLess(self.task.end_date, datetime.datetime.now())

    def test_update_task_resets_dates_on_status_rollback(self):
        wfa_status = self.generate_fixture_task_status_wfa()
        done_status = self.generate_fixture_task_status_done()
        wip_status = self.generate_fixture_task_status_wip()

        task = tasks_service.update_task(
            self.task.id, {"task_status_id": wfa_status["id"]}
        )
        self.assertIsNotNone(task["end_date"])

        task = tasks_service.update_task(
            self.task.id, {"task_status_id": str(done_status.id)}
        )
        self.assertIsNotNone(task["done_date"])

        task = tasks_service.update_task(
            self.task.id, {"task_status_id": str(wip_status.id)}
        )
        self.assertIsNone(task["done_date"])
        self.assertIsNone(task["end_date"])

    def test_update_task_drops_the_task_cache(self):
        wip_status = self.generate_fixture_task_status_wip()
        tasks_service.get_task(self.task_id)

        tasks_service.update_task(
            self.task_id, {"task_status_id": str(wip_status.id)}
        )

        self.assertEqual(
            tasks_service.get_task(self.task_id)["task_status_id"],
            str(wip_status.id),
        )

    def test_publish_task(self):
        events = self.capture_events("task:to-review")

        tasks_service.task_to_review(
            self.task.id, self.person.serialize(), "my comment"
        )

        self.assertEqual(
            str(Task.get(self.task.id).task_status_id),
            self.to_review_status_id,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["previous_task_status_id"], self.open_status_id
        )
        self.assertEqual(events[0]["comment"], "my comment")

    def test_reset_tasks_data(self):
        """
        The command that rebuilds the fields derived from the comment
        history, for every task of a production at once.
        """
        comments_service.new_comment(
            self.task_id, self.wip_status_id, self.person.id, "wip"
        )
        self.task.update({"task_status_id": self.open_status_id})
        self.shot_task.update({"retake_count": 42})

        tasks_service.reset_tasks_data(self.project_id)

        self.assertEqual(
            str(Task.get(self.task_id).task_status_id), self.wip_status_id
        )
        self.assertEqual(Task.get(self.shot_task.id).retake_count, 0)


class TaskReaderTestCase(TaskTestCase):
    def test_get_task_cache_is_keyed_by_the_string_id(self):
        # A UUID and its string used to be two cache entries, and only the
        # string one was ever dropped by clear_task_cache.
        tasks_service.get_task(uuid.UUID(self.task_id))
        self.task.update({"name": "renamed"})
        tasks_service.clear_task_cache(self.task_id)
        self.assertEqual(
            tasks_service.get_task(uuid.UUID(self.task_id))["name"], "renamed"
        )

    def test_get_task(self):
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, "wrong-id"
        )

        task = tasks_service.get_task(self.task_id)

        self.assertEqual(task["id"], self.task_id)

    def test_get_task_of_a_removed_task(self):
        deletion_service.remove_task(self.task_id)

        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, self.task_id
        )

    def test_get_task_by_shotgun_id(self):
        self.task.update({"shotgun_id": 12})

        self.assertEqual(
            tasks_service.get_task_by_shotgun_id(12)["id"], self.task_id
        )
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task_by_shotgun_id, 13
        )

    def test_get_department_from_task(self):
        department = tasks_service.get_department_from_task(self.task.id)
        self.assertEqual(department["name"], "Modeling")

    def test_get_full_task(self):
        task = tasks_service.get_full_task(self.task.id, self.person.id)
        self.assertEqual(task["project"]["name"], self.project.name)
        self.assertEqual(task["assigner"]["id"], str(self.assigner.id))
        self.assertEqual(task["persons"][0]["id"], self.person_id)
        self.assertEqual(task["task_status"]["id"], self.open_status_id)
        self.assertEqual(task["task_type"]["id"], str(self.task_type.id))
        self.assertEqual(task["is_subscribed"], False)

        task = tasks_service.get_full_task(self.shot_task.id, self.person.id)
        self.assertEqual(task["sequence"]["id"], str(self.sequence.id))

    def test_get_tasks_for_shot(self):
        tasks = tasks_service.get_tasks_for_shot(self.shot.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.shot_task.id))

    def test_get_tasks_for_sequence(self):
        self.generate_fixture_sequence_task()
        tasks = tasks_service.get_tasks_for_sequence(self.sequence.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.sequence_task.id))

    def test_get_tasks_for_scene(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        tasks = tasks_service.get_tasks_for_scene(self.scene.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.scene_task.id))

    def test_get_task_dicts_for_entity(self):
        tasks = tasks_service.get_task_dicts_for_entity(self.asset.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], self.task_id)
        self.assertEqual(tasks[0]["task_type_name"], "Shaders")
        self.assertEqual(tasks[0]["entity_name"], "Tree")

    def test_get_task_dicts_for_entity_utf8(self):
        self.task.delete()
        task_type = TaskType.create(
            name="Modélisation",
            color="#FFFFFF",
            department_id=self.department.id,
        )
        Task.create(
            name="Première Tâche",
            project_id=self.project.id,
            task_type_id=task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

        tasks = tasks_service.get_task_dicts_for_entity(self.asset.id)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Première Tâche")
        self.assertEqual(tasks[0]["task_type_name"], "Modélisation")

    def test_get_task_dicts_for_entity_is_sorted_by_name(self):
        """
        The detailed task listings promise a name-ordered output, wherever
        the sort happens.
        """
        self.generate_fixture_task(name="B task")
        self.generate_fixture_task(name="A task")

        tasks = tasks_service.get_task_dicts_for_entity(self.asset.id)

        names = [task["name"] for task in tasks]
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertLess(names.index("A task"), names.index("B task"))

    def test_get_task_dicts_for_entity_with_relations_attaches_assignees(self):
        self.generate_fixture_task(name="Secondary")

        tasks = tasks_service.get_task_dicts_for_entity(
            self.asset.id, relations=True
        )

        self.assertEqual(len(tasks), 2)
        for task in tasks:
            self.assertEqual(task["assignees"], [self.person_id])

    def test_get_task_dicts_for_entity_relations_avoids_n_plus_one(self):
        self.generate_fixture_task(name="Secondary")
        self.generate_fixture_task(name="Tertiary")

        with self.collect_statements() as statements:
            tasks = tasks_service.get_task_dicts_for_entity(
                self.asset.id, relations=True
            )

        self.assertEqual(len(tasks), 3)
        link_statements = [
            statement
            for statement in statements
            if "task_person_link" in statement.lower()
        ]
        self.assertLessEqual(
            len(link_statements),
            1,
            f"Expected at most 1 task_person_link query, got "
            f"{len(link_statements)}: {link_statements}",
        )

    def test_the_project_readers_answer_for_one_production(self):
        """
        The three paginated readers behind the production pages. Each is
        scoped by the task, so a row hanging from another production's task
        must stay out.
        """
        self.generate_fixture_comment()
        time_spents_service.create_or_update_time_spent(
            self.task_id, self.person_id, "2018-06-04", 600
        )

        self.generate_fixture_project_standard()
        other_task = self.generate_fixture_task_standard()
        comments_service.new_comment(
            other_task.id,
            self.task_status.id,
            self.user["id"],
            "elsewhere",
        )
        time_spents_service.create_or_update_time_spent(
            str(other_task.id), self.person_id, "2018-06-04", 600
        )

        self.assertEqual(
            {
                comment["object_id"]
                for comment in comments_service.get_comments_for_project(
                    self.project_id
                )
            },
            {self.task_id},
        )
        self.assertEqual(
            {
                time_spent["task_id"]
                for time_spent in time_spents_service.get_time_spents_for_project(
                    self.project_id
                )
            },
            {self.task_id},
        )
        self.assertNotIn(
            str(other_task.id),
            [
                task["id"]
                for task in todos_service.get_tasks_for_project(
                    self.project_id
                )
            ],
        )


class TaskTypeReaderTestCase(TaskTestCase):
    def test_get_task_types_for_entity(self):
        task_types = tasks_service.get_task_types_for_entity(self.asset.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type.id))

        # Two tasks of the same type on the entity name the type once.
        self.generate_fixture_task(name="Second")
        task_types = tasks_service.get_task_types_for_entity(self.asset.id)
        self.assertEqual(len(task_types), 1)

    def test_get_task_types_for_shot(self):
        task_types = tasks_service.get_task_types_for_shot(self.shot.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type_animation.id))

    def test_get_task_types_for_scene(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        task_types = tasks_service.get_task_types_for_scene(self.scene.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type_animation.id))

    def test_get_task_types_for_sequence(self):
        self.generate_fixture_sequence_task()
        task_types = tasks_service.get_task_types_for_sequence(
            self.sequence.id
        )
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type_animation.id))

    def test_get_task_types_for_project(self):
        """
        The task types a production actually has tasks for, not the ones its
        settings allow.
        """
        self.generate_fixture_project_standard()
        # A task of another production, on a task type this one does not use.
        other_task = self.generate_fixture_task_standard()
        other_task.update({"task_type_id": self.task_type_layout.id})

        task_types = tasks_service.get_task_types_for_project(self.project_id)

        self.assertEqual(
            sorted(task_type["name"] for task_type in task_types),
            ["Animation", "Shaders"],
        )


class CommentReaderTestCase(TaskTestCase):

    def test_get_comment_by_preview_file_id(self):
        preview_file = self.generate_fixture_preview_file()
        self.generate_fixture_comment()
        self.assertIsNone(
            tasks_service.get_comment_by_preview_file_id(preview_file.id)
        )

        comment = Comment.get(self.comment["id"])
        comment.previews = [preview_file]
        comment.save()

        self.assertEqual(
            tasks_service.get_comment_by_preview_file_id(preview_file.id)[
                "id"
            ],
            self.comment["id"],
        )


class ResetTaskDataTestCase(ApiDBTestCase):
    """
    reset_task_data rebuilds a task's derived fields from its comment
    history and its time spents, which is what repairs a task whose counters
    drifted.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_retake()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)

    def comment_with(self, task_status):
        return comments_service.new_comment(
            self.task_id, str(task_status.id), self.person.id, "comment"
        )

    def test_a_run_of_retakes_counts_once(self):
        """
        The retake count follows the number of times the task went back to
        retake, not the number of retake comments: two in a row are one
        return trip.
        """
        for task_status in [
            self.task_status_wip,
            self.task_status_retake,
            self.task_status_retake,
            self.task_status_wip,
            self.task_status_retake,
        ]:
            self.comment_with(task_status)

        tasks_service.reset_task_data(self.task_id)

        task = tasks_service.get_task(self.task_id)
        self.assertEqual(task["retake_count"], 2)
        self.assertIsNotNone(task["real_start_date"])

    def test_the_duration_is_the_sum_of_the_time_spents(self):
        for date, duration in [("2024-01-08", 120), ("2024-01-09", 300)]:
            time_spents_service.create_or_update_time_spent(
                self.task_id, str(self.person.id), date, duration
            )
        self.task.update({"duration": 0})

        tasks_service.reset_task_data(self.task_id)

        task = tasks_service.get_task(self.task_id)
        self.assertEqual(task["duration"], 420)


class TaskPreviewRevisionTestCase(ApiDBTestCase):
    """
    The revision and position a preview takes on a task. A revision is
    unique per task, positions are contiguous within one revision.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)

    def test_get_next_revision(self):
        self.assertEqual(
            tasks_service.get_next_preview_revision(self.task_id), 1
        )

        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2)

        self.assertEqual(
            tasks_service.get_next_preview_revision(self.task_id), 3
        )

    def test_get_next_position(self):
        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2)
        self.generate_fixture_preview_file(revision=2, name="second")

        self.assertEqual(tasks_service.get_next_position(self.task_id, 2), 3)

    def test_check_revision_is_unique_for_task(self):
        """
        A revision number is taken once per task, and free everywhere else.
        """
        self.generate_fixture_preview_file(revision=1, position=1)

        with self.assertRaises(RevisionAlreadyExistsException):
            tasks_service.check_revision_is_unique_for_task(
                self.task_id, revision=1
            )

        tasks_service.check_revision_is_unique_for_task(
            self.task_id, revision=2
        )

    def test_check_revision_excludes_the_preview_being_updated(self):
        preview = self.generate_fixture_preview_file(revision=1, position=1)

        tasks_service.check_revision_is_unique_for_task(
            self.task_id,
            revision=1,
            exclude_preview_id=str(preview.id),
        )

    def test_check_revision_ignores_the_extra_previews(self):
        """
        Only the main preview of a revision takes the revision number: the
        extra ones share it by design.
        """
        self.generate_fixture_preview_file(revision=1, position=2)

        tasks_service.check_revision_is_unique_for_task(
            self.task_id, revision=1
        )

    def test_the_setting_read_here_is_the_one_the_production_was_given(self):
        """
        Whether the preview lands on the entity is a production setting, and
        get_project is memoized on the id it is handed: reading it under a
        key nobody invalidates keeps the setting from before the change for
        the length of the TTL.
        """
        preview_file = self.generate_fixture_preview_file().serialize()
        project_id = str(self.project.id)
        tasks_service.update_preview_file_info(preview_file)

        projects_service.update_project(
            project_id, {"is_set_preview_automated": True}
        )
        entity = tasks_service.update_preview_file_info(preview_file)

        self.assertEqual(entity["preview_file_id"], preview_file["id"])
