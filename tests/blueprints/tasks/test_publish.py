import os

from tests.base import ApiDBTestCase
from zou.app.services import (
    assets_service,
    projects_service,
    tasks_service,
)


class RouteTaskChangeTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task()

        self.wip_status_id = str(self.task_status_wip.id)

    def test_add_preview_to_comment(self):
        # Comment
        self.project_id = self.project.id
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        comment = self.post(path, data)

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
        path = f"/pictures/preview-files/{preview_file['id']}"
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
        path = f"/actions/tasks/{self.task.id}/comment/"
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
        path = f"/pictures/preview-files/{preview_file['id']}"
        self.upload_file(path, file_path_fixture)
        task = tasks_service.get_task(task_id)
        asset = assets_service.get_asset(str(self.task.entity_id))
        self.assertEqual(asset["preview_file_id"], preview_file["id"])
        self.assertEqual(task["last_preview_file_id"], preview_file["id"])

        # Delete preview
        path = f"/data/preview-files/{preview_file['id']}"
        self.delete(path)
        task = tasks_service.get_task(task_id)
        asset = assets_service.get_asset(str(self.task.entity_id))
        self.assertEqual(asset["preview_file_id"], first_preview_id)
        self.assertEqual(task["last_preview_file_id"], first_preview_id)
