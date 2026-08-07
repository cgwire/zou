# -*- coding: UTF-8 -*-
import datetime

from unittest import mock

from sqlalchemy import event
from sqlalchemy.orm.exc import StaleDataError

from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.comment import Comment
from zou.app.models.studio import Studio
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    comments_service,
    deletion_service,
    persons_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import fields

from zou.app.services.exception import (
    RevisionAlreadyExistsException,
    StudioNotFoundException,
    TaskNotFoundException,
)


class TaskTestCase(ApiDBTestCase):
    """
    An asset and a shot, each carrying one task. Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

        self.project_id = str(self.project.id)
        self.task_id = str(self.task.id)
        self.person_id = str(self.person.id)
        self.open_status_id = str(self.task_status.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.to_review_status_id = str(self.task_status_to_review.id)

    def collect_statements(self):
        """
        Record every statement the session sends until the returned context
        manager exits. Used to catch the queries a reader must not run.
        """
        statements = []

        def collect(conn, cursor, statement, *args, **kwargs):
            statements.append(statement)

        engine = db.session.get_bind()

        class Recorder:
            def __enter__(inner):
                event.listen(engine, "before_cursor_execute", collect)
                return statements

            def __exit__(inner, *args):
                event.remove(engine, "before_cursor_execute", collect)

        return Recorder()


class TaskCreationTestCase(TaskTestCase):
    def test_create_task(self):
        shot = self.shot.serialize()
        task_type = self.task_type.serialize()
        status = tasks_service.get_default_status()

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
        status = tasks_service.get_default_status()

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

    def test_get_studio(self):
        studio = Studio.create(name="Blue Spirit", color="#000000")

        self.assertEqual(
            tasks_service.get_studio(studio.id)["name"], "Blue Spirit"
        )
        self.assertRaises(
            StudioNotFoundException,
            tasks_service.get_studio,
            fields.gen_uuid(),
        )

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

    def test_get_tasks_for_project_loads_only_assignee_ids(self):
        with self.collect_statements() as statements:
            tasks = tasks_service.get_tasks_for_project(self.project.id)

        assignees = [
            assignee for task in tasks for assignee in task["assignees"]
        ]
        self.assertIn(self.person_id, assignees)
        self.assertTrue(
            all(isinstance(assignee, str) for assignee in assignees)
        )

        person_link_statements = [
            statement
            for statement in statements
            if "task_person_link" in statement.lower()
        ]
        self.assertTrue(person_link_statements)
        for statement in person_link_statements:
            self.assertNotIn("person.password", statement)

    def test_the_project_readers_answer_for_one_production(self):
        """
        The three paginated readers behind the production pages. Each is
        scoped by the task, so a row hanging from another production's task
        must stay out.
        """
        self.generate_fixture_comment()
        tasks_service.create_or_update_time_spent(
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
        tasks_service.create_or_update_time_spent(
            str(other_task.id), self.person_id, "2018-06-04", 600
        )

        self.assertEqual(
            {
                comment["object_id"]
                for comment in tasks_service.get_comments_for_project(
                    self.project_id
                )
            },
            {self.task_id},
        )
        self.assertEqual(
            {
                time_spent["task_id"]
                for time_spent in tasks_service.get_time_spents_for_project(
                    self.project_id
                )
            },
            {self.task_id},
        )
        self.assertNotIn(
            str(other_task.id),
            [
                task["id"]
                for task in tasks_service.get_tasks_for_project(
                    self.project_id
                )
            ],
        )


class TaskTypeReaderTestCase(TaskTestCase):
    def test_get_task_types_for_entity(self):
        task_types = tasks_service.get_task_types_for_entity(self.asset.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type.id))

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


class PersonTaskTestCase(TaskTestCase):
    def test_get_person_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            tasks_service.get_person_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            len(tasks_service.get_person_tasks(self.user["id"], projects)), 1
        )

        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "last comment"
        )

        tasks = tasks_service.get_person_tasks(self.person.id, projects)
        tasks = sorted(tasks, key=lambda task: task["task_type_name"])
        self.assertEqual(len(tasks), 2)
        # Animation comes first, so the commented task is the second one.
        self.assertEqual(tasks[1]["last_comment"]["text"], "last comment")
        self.assertEqual(tasks[1]["last_comment"]["person_id"], self.person_id)

    def test_get_person_done_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            tasks_service.get_person_done_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            tasks_service.get_person_done_tasks(self.user["id"], projects), []
        )

        done_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task.id, {"task_status_id": done_status["id"]}
        )

        self.assertEqual(
            len(
                tasks_service.get_person_done_tasks(self.user["id"], projects)
            ),
            1,
        )


class TimeSpentTestCase(TaskTestCase):
    def test_create_or_update_time_spent(self):
        time_spent = tasks_service.create_or_update_time_spent(
            self.task_id, self.person_id, "2017-09-23", 3600
        )
        self.assertEqual(time_spent["duration"], 3600)

        # A second write on the same day replaces the duration...
        time_spent = tasks_service.create_or_update_time_spent(
            self.task_id, self.person_id, "2017-09-23", 7200
        )
        self.assertEqual(time_spent["duration"], 7200)

        # ...unless it is asked to add to it.
        time_spent = tasks_service.create_or_update_time_spent(
            self.task_id, self.person_id, "2017-09-23", 7200, add=True
        )
        self.assertEqual(time_spent["duration"], 14400)

    def test_the_task_duration_follows_its_time_spents(self):
        # The duration of the task is the sum of its time spents, and it is
        # read through the memoized task.
        tasks_service.get_task(self.task_id)

        for person_id, date, duration in [
            (self.person_id, "2017-09-23", 3600),
            (str(self.user["id"]), "2017-09-24", 7200),
        ]:
            tasks_service.create_or_update_time_spent(
                self.task_id, person_id, date, duration
            )

        self.assertEqual(
            tasks_service.get_task(self.task_id)["duration"], 10800
        )

        tasks_service.delete_time_spent(
            self.task_id, self.person_id, "2017-09-23"
        )

        self.assertEqual(
            tasks_service.get_task(self.task_id)["duration"], 7200
        )

    def test_get_time_spents(self):
        """
        Time spents of a task come back grouped by person, with the total
        alongside. The optional date narrows the group without touching the
        grouping itself.
        """
        user_id = str(self.user["id"])
        first_day = datetime.date(2017, 9, 23)
        second_day = datetime.date(2017, 9, 24)
        for person_id, date, duration in [
            (self.person_id, first_day, 3600),
            (user_id, first_day, 7200),
            (user_id, second_day, 7200),
        ]:
            TimeSpent.create(
                person_id=person_id,
                task_id=self.task_id,
                date=date,
                duration=duration,
            )

        time_spents = tasks_service.get_time_spents(self.task_id)
        self.assertEqual(time_spents["total"], 18000)
        self.assertEqual(len(time_spents[self.person_id]), 1)
        self.assertEqual(len(time_spents[user_id]), 2)

        one_day = tasks_service.get_time_spents(self.task_id, first_day)
        self.assertEqual(one_day["total"], 10800)
        self.assertEqual(len(one_day[user_id]), 1)


class CommentReaderTestCase(TaskTestCase):
    def test_get_comments_by_role(self):
        """
        An artist does not read what a client wrote, and a client only reads
        what is meant for clients or written by another client.
        """
        self.generate_fixture_user_client()
        self.generate_fixture_comment()
        self.generate_fixture_comment()
        self.generate_fixture_comment(person=self.user_client)
        self.generate_fixture_comment()

        self.assertEqual(
            len(tasks_service.get_comments(self.task_id, is_manager=True)), 4
        )
        self.assertEqual(
            len(tasks_service.get_comments(self.task_id, is_manager=False)), 3
        )

        with mock.patch.object(
            persons_service, "get_current_user", return_value=self.user_client
        ):
            comments = tasks_service.get_comments(self.task_id, is_client=True)
        self.assertEqual(len(comments), 1)

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

    def test_a_preview_added_to_a_comment_drops_its_cache(self):
        # The comment is read through a memoized serialization, and the
        # comment:update event emitted right after the upload makes every
        # client refetch: without the drop they all cache a comment with no
        # preview on it.
        comment_id = self.generate_fixture_comment()["id"]
        tasks_service.get_comment(comment_id, relations=True)

        preview_file = tasks_service.add_preview_file_to_comment(
            comment_id, self.person_id, self.task_id
        )

        comment = tasks_service.get_comment(comment_id, relations=True)
        self.assertEqual(comment["previews"], [preview_file["id"]])


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
            tasks_service.create_or_update_time_spent(
                self.task_id, str(self.person.id), date, duration
            )
        self.task.update({"duration": 0})

        tasks_service.reset_task_data(self.task_id)

        task = tasks_service.get_task(self.task_id)
        self.assertEqual(task["duration"], 420)


class GetOrCreateTaskTypeTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.department = tasks_service.get_or_create_department(
            "Concept", "#8D6E63"
        )

    def test_create_when_missing(self):
        task_type = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        self.assertIsNotNone(task_type["id"])
        self.assertEqual(task_type["for_entity"], "Asset")

    def test_return_existing_with_same_name_and_entity(self):
        first = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        second = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(TaskType.get_all_by(name="Concept")), 1)

    def test_same_name_different_for_entity_coexist(self):
        asset_type = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )
        concept_type = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1, for_entity="Concept"
        )
        self.assertNotEqual(asset_type["id"], concept_type["id"])
        self.assertEqual(asset_type["for_entity"], "Asset")
        self.assertEqual(concept_type["for_entity"], "Concept")
        self.assertEqual(len(TaskType.get_all_by(name="Concept")), 2)

    def test_a_new_task_type_joins_the_listing(self):
        tasks_service.get_task_types()

        task_type = tasks_service.get_or_create_task_type(
            self.department, "Concept", "#8D6E63", 1
        )

        self.assertIn(
            task_type["id"],
            [listed["id"] for listed in tasks_service.get_task_types()],
        )


class TaskStatusTestCase(ApiDBTestCase):
    """
    The statuses a studio works with. get_or_create_status names them by
    short name, so asking for a second long name of an existing short one
    returns the first.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_task_status()
        # Named WIP with short name wip, which is what makes the second
        # test below get it back under a different long name.
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()

    def test_get_status(self):
        task_status = tasks_service.get_or_create_status(
            "WIP", "wip", is_wip=True
        )
        self.assertEqual(task_status["name"], "WIP")

    def test_get_wip_status(self):
        task_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )
        self.assertEqual(task_status["name"], "WIP")

    def test_get_done_status(self):
        task_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        self.assertEqual(task_status["name"], "Done")

    def test_get_todo_status(self):
        task_status = tasks_service.get_default_status()
        self.assertEqual(task_status["is_default"], True)

    def test_get_to_review_status(self):
        task_status = tasks_service.get_to_review_status()
        self.assertEqual(task_status["name"], "To review")

    def test_a_new_status_joins_the_listing(self):
        # The listing is memoized and feeds the status dropdowns of every
        # client, so a status created outside the CRUD route has to drop it
        # too.
        tasks_service.get_task_statuses()

        task_status = tasks_service.get_or_create_status(
            "Omitted", "omt", "#22d160"
        )

        self.assertIn(
            task_status["id"],
            [listed["id"] for listed in tasks_service.get_task_statuses()],
        )


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
