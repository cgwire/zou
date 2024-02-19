import os

from tests.base import ApiDBTestCase

from zou.app.services import (
    assets_service,
    persons_service,
    projects_service,
    tasks_service,
)


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

    def generate_team(self):
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        user_cg_artist = persons_service.get_person_raw(
            self.user_cg_artist["id"]
        )
        user_manager = persons_service.get_person_raw(self.user_manager["id"])
        self.project.team = [self.person, user_cg_artist, user_manager]
        self.project.save()

    def assert_event_is_fired(self):
        self.assertTrue(self.is_event_fired)

    def test_add_preview_to_comment(self):
        # Comment
        self.project_id = self.project.id
        path = "/actions/tasks/%s/comment/" % self.task.id
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        comment = self.post(path, data)

        # Add preview to comment
        data = {}
        comment_id = comment["id"]
        task_id = str(self.task.id)
        path = f"/actions/tasks/{task_id}/comments/{comment_id}/add-preview"
        preview_file = self.post(path, data)
        self.assertIsNotNone(preview_file["id"])
        task = tasks_service.get_task(self.task.id)
        asset = assets_service.get_asset(self.task.entity_id)
        self.assertIsNone(asset["preview_file_id"])
        self.assertIsNone(task["last_preview_file_id"])

        # Upload file to preview
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        path = "/pictures/preview-files/%s" % preview_file["id"]
        self.upload_file(path, file_path_fixture)
        task = tasks_service.get_task(task_id)
        asset = assets_service.get_asset(self.task.entity_id)
        self.assertIsNone(asset["preview_file_id"])
        self.assertEqual(task["last_preview_file_id"], preview_file["id"])
        first_preview_id = preview_file["id"]

        # Set preview automated at project level
        projects_service.update_project(
            self.project_id, {"is_set_preview_automated": True}
        )

        # Add a new comment
        path = "/actions/tasks/%s/comment/" % self.task.id
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test 2",
        }
        comment = self.post(path, data)
        comment_id = comment["id"]

        # Add preview to comment
        path = f"/actions/tasks/{task_id}/comments/{comment_id}/add-preview"
        data = {}
        preview_file = self.post(path, data)

        # Upload file to preview
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        path = "/pictures/preview-files/%s" % preview_file["id"]
        self.upload_file(path, file_path_fixture)
        task = tasks_service.get_task(task_id)
        asset = assets_service.get_asset(str(self.task.entity_id))
        self.assertEqual(asset["preview_file_id"], preview_file["id"])
        self.assertEqual(task["last_preview_file_id"], preview_file["id"])

        # Delete preview
        path = "/data/preview-files/%s" % preview_file["id"]
        self.delete(path)
        task = tasks_service.get_task(task_id)
        asset = assets_service.get_asset(str(self.task.entity_id))
        self.assertEqual(asset["preview_file_id"], first_preview_id)
        self.assertEqual(task["last_preview_file_id"], first_preview_id)
