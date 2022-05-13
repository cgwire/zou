# -*- coding: UTF-8 -*-
import datetime

from tests.base import ApiDBTestCase

from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.models.time_spent import TimeSpent
from zou.app.models.preview_file import PreviewFile
from zou.app.services import (
    comments_service,
    deletion_service,
    preview_files_service,
    tasks_service,
)
from zou.app.utils import events, fields

from zou.app.services.exception import TaskNotFoundException


class ToReviewHandler(object):
    def __init__(self, open_status_id, to_review_status_id):
        self.is_event_fired = False
        self.open_status_id = open_status_id
        self.to_review_status_id = to_review_status_id

    def handle_event(self, data):
        self.is_event_fired = True
        self.data = data


class TaskServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(TaskServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
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
        self.generate_fixture_file_status()
        self.generate_fixture_software()
        self.generate_fixture_working_file()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()

        self.project_id = str(self.project.id)
        self.task_id = str(self.task.id)
        self.open_status_id = self.task_status.id
        self.wip_status_id = self.task_status_wip.id
        self.to_review_status_id = self.task_status_to_review.id

        self.is_event_fired = False
        events.unregister_all()

    def handle_event(self, data):
        self.is_event_fired = True
        self.assertEqual(
            data["previous_task_status_id"], str(self.open_status_id)
        )

    def assert_event_is_fired(self):
        self.assertTrue(self.is_event_fired)

    def test_get_status(self):
        task_status = tasks_service.get_or_create_status("WIP", "wip")
        self.assertEqual(task_status["name"], "WIP")

    def test_get_wip_status(self):
        task_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc"
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
        task = tasks[0]
        task = tasks_service.get_task(task["id"])
        self.assertEqual(task["entity_id"], shot["id"])
        self.assertEqual(task["task_type_id"], task_type["id"])
        self.assertEqual(task["project_id"], shot["project_id"])
        self.assertEqual(task["task_status_id"], status["id"])

    def test_publish_task(self):
        handler = ToReviewHandler(
            self.open_status_id, self.to_review_status_id
        )
        events.register("task:to-review", "mark_event_as_fired", handler)
        tasks_service.task_to_review(
            self.task.id, self.person.serialize(), "my comment"
        )
        self.is_event_fired = handler.is_event_fired
        data = handler.data

        task = Task.get(self.task.id)
        self.assertEqual(task.task_status_id, self.to_review_status_id)
        self.assert_event_is_fired()

        self.assertEqual(
            data["previous_task_status_id"], str(self.open_status_id)
        )

        self.assertEqual(data["comment"], "my comment")

    def test_assign_task(self):
        tasks_service.assign_task(self.task.id, self.assigner.id)
        self.assertEqual(self.task.assignees[1].id, self.assigner.id)

    def test_get_department_from_task(self):
        department = tasks_service.get_department_from_task(self.task.id)
        self.assertEqual(department["name"], "Modeling")

    def test_get_task(self):
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, "wrong-id"
        )
        task = tasks_service.get_task(self.task_id)
        self.assertEqual(str(self.task_id), task["id"])
        self.output_file.delete()
        self.working_file.delete()
        deletion_service.remove_task(task["id"])

        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, str(self.task_id)
        )

    def test_get_tasks_for_sequence(self):
        self.generate_fixture_sequence_task()
        tasks = tasks_service.get_tasks_for_sequence(self.sequence.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.sequence_task.id))

    def test_get_tasks_for_shot(self):
        tasks = tasks_service.get_tasks_for_shot(self.shot.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.shot_task.id))

    def test_get_tasks_for_scene(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_task()
        tasks = tasks_service.get_tasks_for_scene(self.scene.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.scene_task.id))

    def test_get_dict_tasks_for_asset(self):
        tasks = tasks_service.get_task_dicts_for_entity(self.asset.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], str(self.task.id))
        self.assertEqual(tasks[0]["task_type_name"], str("Shaders"))
        self.assertEqual(tasks[0]["entity_name"], str("Tree"))

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

    def test_get_task_types_for_entity(self):
        task_types = tasks_service.get_task_types_for_entity(self.asset.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0]["id"], str(self.task_type.id))

    def test_get_task_dicts_for_entity_utf8(self):
        start_date = fields.get_date_object("2017-02-20")
        due_date = fields.get_date_object("2017-02-28")
        real_start_date = fields.get_date_object("2017-02-22")
        self.working_file.delete()
        self.output_file.delete()
        self.task.delete()
        self.task_type = TaskType(
            name="Modélisation",
            color="#FFFFFF",
            department_id=self.department.id,
        )
        self.task_type.save()
        self.task = Task(
            name="Première Tâche",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
            duration=50,
            estimation=40,
            start_date=start_date,
            due_date=due_date,
            real_start_date=real_start_date,
        )
        self.task.save()

        tasks = tasks_service.get_task_dicts_for_entity(self.asset.id)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["name"], "Première Tâche")
        self.assertEqual(tasks[0]["task_type_name"], "Modélisation")

    def test_get_or_create_time_spents(self):
        person_id = self.person.id
        task_id = self.task.id

        duration = 3600
        time_spent = tasks_service.create_or_update_time_spent(
            person_id=person_id,
            task_id=task_id,
            date="2017-09-23",
            duration=duration,
        )
        self.assertEqual(time_spent["duration"], duration)

        duration = 7200
        time_spent = tasks_service.create_or_update_time_spent(
            person_id=person_id,
            task_id=task_id,
            date="2017-09-23",
            duration=duration,
        )
        self.assertEqual(time_spent["duration"], duration)

        duration = 7200
        time_spent = tasks_service.create_or_update_time_spent(
            person_id=person_id,
            task_id=task_id,
            date="2017-09-23",
            duration=duration,
            add=True,
        )
        self.assertEqual(time_spent["duration"], 2 * duration)

    def test_get_time_spents(self):
        pass
        """
        person_id = self.person.id
        user_id = self.user["id"]
        task_id = self.task.id
        ts1 = TimeSpent.create(
            person_id=person_id,
            task_id=task_id,
            date=datetime.date(2017, 9, 23),
            duration=3600
        )
        ts2 = TimeSpent.create(
            person_id=user_id,
            task_id=task_id,
            date=datetime.date(2017, 9, 23),
            duration=7200
        )
        ts3 = TimeSpent.create(
            person_id=user_id,
            task_id=task_id,
            date=datetime.date(2017, 9, 24),
            duration=7200
        )
        time_spents = self.get(
            "/data/time-spents?task_id=%s" % task_id
        )
        self.assertEqual(
            time_spents["total"],
            sum([ts.duration for ts in [ts1, ts2, ts3]]))
        self.assertEqual(len(time_spents[str(user_id)]), 1)
        self.assertEqual(len(time_spents[str(person_id)]), 2)
        """

    def test_clear_assignation(self):
        task_id = self.task.id
        tasks_service.assign_task(self.task.id, self.person.id)
        tasks_service.clear_assignation(task_id)
        task = tasks_service.get_task_with_relations(task_id)
        self.assertEqual(len(task["assignees"]), 0)

    def test_get_tasks_for_person(self):
        projects = [self.project.serialize()]
        tasks = tasks_service.get_person_tasks(self.user["id"], projects)
        self.assertEqual(len(tasks), 0)

        tasks_service.assign_task(self.task.id, self.user["id"])
        tasks = tasks_service.get_person_tasks(self.user["id"], projects)
        self.assertEqual(len(tasks), 1)

        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "last comment"
        )
        tasks = tasks_service.get_person_tasks(self.person.id, projects)
        # Animation as first task
        tasks = sorted(tasks, key=lambda t: t["task_type_name"])
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[1]["last_comment"]["text"], "last comment")
        self.assertEqual(
            tasks[1]["last_comment"]["person_id"], str(self.person.id)
        )

    def test_get_done_tasks_for_person(self):
        projects = [self.project.serialize()]
        tasks = tasks_service.get_person_done_tasks(self.user["id"], projects)
        self.assertEqual(len(tasks), 0)

        tasks_service.assign_task(self.task.id, self.user["id"])
        tasks = tasks_service.get_person_done_tasks(self.user["id"], projects)
        self.assertEqual(len(tasks), 0)

        done_status = tasks_service.get_or_create_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task.id, {"task_status_id": done_status["id"]}
        )
        tasks = tasks_service.get_person_done_tasks(self.user["id"], projects)
        self.assertEqual(len(tasks), 1)

    def test_update_task(self):
        wfa_status = self.generate_fixture_task_status_wfa()
        tasks_service.update_task(
            self.task.id, {"task_status_id": wfa_status["id"]}
        )
        self.assertEqual(str(self.task.task_status_id), wfa_status["id"])
        self.assertIsNotNone(self.task.end_date)
        self.assertLess(self.task.end_date, datetime.datetime.now())

    def test_remove_task(self):
        self.working_file.delete()
        self.output_file.delete()
        deletion_service.remove_task(self.task_id)
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, self.task_id
        )

    def test_remove_tasks(self):
        self.working_file.delete()
        self.output_file.delete()
        task_id = str(self.task_id)
        task2_id = str(self.generate_fixture_task("main 2").id)
        task_ids = [task_id, task2_id]
        deletion_service.remove_tasks(self.project_id, task_ids)
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, task_id
        )
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, task2_id
        )

    def test_remove_task_force(self):
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        TimeSpent.create(
            person_id=self.person.id,
            task_id=self.task.id,
            date=datetime.date(2017, 9, 23),
            duration=3600,
        )
        deletion_service.remove_task(self.task_id, force=True)
        self.assertRaises(
            TaskNotFoundException, tasks_service.get_task, self.task_id
        )

    def test_delete_all_task_types(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        task_1_id = str(self.task.id)
        task_2_id = str(self.generate_fixture_task(name="second task").id)
        task_3_id = str(self.shot_task.id)
        task_4_id = str(self.generate_fixture_task_standard().id)
        deletion_service.remove_tasks_for_project_and_task_type(
            self.project.id, self.task_type.id
        )
        self.assertIsNone(Task.get(task_1_id))
        self.assertIsNone(Task.get(task_2_id))
        self.assertIsNotNone(Task.get(task_3_id))
        self.assertIsNotNone(Task.get(task_4_id))

    def test_get_comment_mentions(self):
        mentions = comments_service.get_comment_mentions(
            self.task_id, "Test @Emma Doe"
        )
        self.assertEqual(len(mentions), 0)
        mentions = comments_service.get_comment_mentions(
            self.task_id, "Test @John Doe"
        )
        self.assertEqual(mentions[0], self.person)

    def test_get_comments(self):
        self.generate_fixture_user_client()
        self.generate_fixture_comment()
        self.generate_fixture_comment()
        self.generate_fixture_comment(person=self.user_client)
        self.generate_fixture_comment()
        comments = tasks_service.get_comments(self.task_id, is_manager=True)
        self.assertEqual(len(comments), 4)
        comments = tasks_service.get_comments(self.task_id, is_manager=False)
        self.assertEqual(len(comments), 3)
        comments = tasks_service.get_comments(self.task_id, is_client=True)
        self.assertEqual(len(comments), 1)

    def test_new_comment(self):
        comment = comments_service.new_comment(
            self.task_id, self.task_status.id, self.person.id, "Test @John Doe"
        )
        self.assertEqual(comment["mentions"][0], str(self.person.id))

    def test_get_full_task(self):
        task = tasks_service.get_full_task(self.task.id)
        self.assertEqual(task["project"]["name"], self.project.name)
        self.assertEqual(task["assigner"]["id"], str(self.assigner.id))
        self.assertEqual(task["persons"][0]["id"], str(self.person.id))
        self.assertEqual(task["task_status"]["id"], str(self.task_status.id))
        self.assertEqual(task["task_type"]["id"], str(self.task_type.id))

        task = tasks_service.get_full_task(self.shot_task.id)
        self.assertEqual(task["sequence"]["id"], str(self.sequence.id))

    def test_get_next_position(self):
        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2)
        self.generate_fixture_preview_file(revision=2, name="second")
        task_id = self.task.id
        position = tasks_service.get_next_position(task_id, 2)
        self.assertEqual(position, 3)

    def test_update_preview_file_position(self):
        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2)
        preview_file = self.generate_fixture_preview_file(
            revision=2, name="second"
        )
        preview_file_id = str(preview_file.id)
        self.generate_fixture_preview_file(revision=2, name="third")

        preview_files_service.update_preview_file_position(preview_file_id, 1)
        preview_files = PreviewFile.query.filter_by(
            task_id=self.task_id, revision=2
        ).order_by(PreviewFile.position)
        for (i, preview_file) in enumerate(preview_files):
            self.assertEqual(preview_file.position, i + 1)
        self.assertEqual(str(preview_files[0].id), preview_file_id)

        preview_files_service.update_preview_file_position(preview_file_id, 3)
        preview_files = PreviewFile.query.filter_by(
            task_id=self.task_id, revision=2
        ).order_by(PreviewFile.position)
        for (i, preview_file) in enumerate(preview_files):
            self.assertEqual(preview_file.position, i + 1)
        self.assertEqual(str(preview_files[2].id), preview_file_id)
