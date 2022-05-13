import os
import time

from tests.base import ApiDBTestCase

from zou.app.utils import events

from zou.app.models.task import Task
from zou.app.services import projects_service, tasks_service

from PIL import Image


class RouteTaskChangeTestCase(ApiDBTestCase):
    def setUp(self):
        super(RouteTaskChangeTestCase, self).setUp()

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
        self.generate_fixture_task_status_retake()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_todo()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.open_status_id = str(self.task_status.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.retake_status_id = str(self.task_status_retake.id)
        self.done_status_id = str(self.task_status_done.id)

        self.is_event_fired = False
        events.unregister_all()

    def handle_event(self, data):
        self.is_event_fired = True
        self.assertEqual(data["previous_task_status_id"], self.open_status_id)

    def assert_event_is_fired(self):
        self.assertTrue(self.is_event_fired)

    def test_retake_count(self):
        task_id = str(self.task.id)
        self.post(
            "/actions/tasks/%s/comment" % task_id,
            {"task_status_id": self.retake_status_id, "comment": "retake 1"},
        )
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        self.post(
            "/actions/tasks/%s/comment" % task_id,
            {"task_status_id": self.wip_status_id, "comment": "wip 1"},
        )
        comment = self.post(
            "/actions/tasks/%s/comment" % task_id,
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
        )
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 2)
        comment = self.delete(
            "/data/tasks/%s/comments/%s" % (task_id, comment["id"])
        )
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        comment = self.post(
            "/actions/tasks/%s/comment" % task_id,
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
        )
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 2)

    def test_comment_many(self):
        project_id = str(self.project.id)
        task_id = str(self.task.id)
        self.generate_fixture_task(name="second_task")
        task2_id = str(self.task.id)
        path = "/actions/projects/%s/tasks/comment-many" % project_id
        self.post(
            path,
            [
                {
                    "task_status_id": self.retake_status_id,
                    "comment": "retake 1",
                    "object_id": task_id,
                },
                {
                    "task_status_id": self.retake_status_id,
                    "comment": "retake 1",
                    "object_id": task2_id,
                },
            ],
        )
        self.get("data/tasks/%s" % task_id)
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        comments = self.get("data/tasks/%s/comments" % task_id)
        self.assertEqual(len(comments), 1)
        comments = self.get("data/tasks/%s/comments" % task2_id)
        self.assertEqual(len(comments), 1)

    def test_comment_many_as_artist(self):
        project_id = str(self.project.id)
        task_id = str(self.task.id)
        self.generate_fixture_task(name="second_task")
        task2_id = str(self.task.id)
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        new_comments = [
            {
                "task_status_id": self.retake_status_id,
                "comment": "retake 1",
                "object_id": task_id,
            },
            {
                "task_status_id": self.retake_status_id,
                "comment": "retake 1",
                "object_id": task2_id,
            },
        ]
        path = "/actions/projects/%s/tasks/comment-many" % project_id
        self.assign_task_to_artist(task_id)
        self.post(path, new_comments)
        self.log_in_admin()
        self.get("data/tasks/%s" % task_id)
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        comments = self.get("data/tasks/%s/comments" % task_id)
        self.assertEqual(len(comments), 1)
        comments = self.get("data/tasks/%s/comments" % task2_id)
        self.assertEqual(len(comments), 0)

    def test_attachments(self):
        self.delete_test_folder()
        self.create_test_folder()
        task_id = str(self.task.id)
        project_id = str(self.project.id)
        self.upload_file(
            "/actions/tasks/%s/comment" % task_id,
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            extra_fields={
                "task_status_id": self.retake_status_id,
                "comment": "retake 1",
            },
        )
        attachment = self.get("data/attachment-files")[0]
        attachment = self.get("data/attachment-files/%s" % attachment["id"])
        path = "/data/attachment-files/%s/file/th01.png" % attachment["id"]
        result_file_path = self.get_file_path("th01.png")

        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (180, 101))

        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        self.get("data/attachment-files/%s" % attachment["id"], 403)
        projects_service.add_team_member(project_id, self.user_vendor["id"])
        tasks_service.assign_task(task_id, self.user_vendor["id"])
        self.get("data/attachment-files/%s" % attachment["id"])
        self.delete_test_folder()
