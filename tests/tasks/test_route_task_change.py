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
        self.assertEqual(
            data["previous_task_status_id"],
            self.open_status_id
        )

    def assert_event_is_fired(self):
        self.assertTrue(self.is_event_fired)

    def test_status_to_wip(self):
        self.task.real_start_date = None
        events.register(
            "task:start",
            "mark_event_as_fired",
            self
        )

        now = self.now()
        time.sleep(1)
        self.put("/actions/tasks/%s/start" % self.task.id, {})
        task = self.get("data/tasks/%s" % self.task.id)

        self.assertEqual(task["task_status_id"], self.wip_status_id)
        self.assertGreater(task["real_start_date"], now)
        self.assert_event_is_fired()

    def test_status_to_wip_again(self):
        self.task.real_start_date = None
        task_id = str(self.task.id)
        self.put("/actions/tasks/%s/start" % task_id, {})
        real_start_date = Task.get(task_id).real_start_date
        self.put("/actions/tasks/%s/start" % task_id, {})
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(
            real_start_date.replace(microsecond=0).isoformat(),
            task["real_start_date"]
        )

    def test_retake_count(self):
        task_id = str(self.task.id)
        self.post("/actions/tasks/%s/comment" % task_id, {
            "task_status_id": self.retake_status_id,
            "comment": "retake 1"
        })
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        self.post("/actions/tasks/%s/comment" % task_id, {
            "task_status_id": self.wip_status_id,
            "comment": "wip 1"
        })
        comment = self.post("/actions/tasks/%s/comment" % task_id, {
            "task_status_id": self.retake_status_id,
            "comment": "retake 2"
        })
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 2)
        comment = self.delete("/data/tasks/%s/comments/%s" % (
            task_id,
            comment["id"]
        ))
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 1)
        comment = self.post("/actions/tasks/%s/comment" % task_id, {
            "task_status_id": self.retake_status_id,
            "comment": "retake 2"
        })
        task = self.get("data/tasks/%s" % task_id)
        self.assertEqual(task["retake_count"], 2)

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
                "comment": "retake 1"
            }
        )
        attachment = self.get("data/attachment-files")[0]
        attachment = self.get("data/attachment-files/%s" % attachment["id"])
        path = "/data/attachment-files/%s/file" % attachment["id"]
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
