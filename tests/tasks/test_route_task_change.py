import os

from tests.base import ApiDBTestCase


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

    def test_retake_count(self):
        task_id = str(self.task.id)
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 1"},
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 1)
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.wip_status_id, "comment": "wip 1"},
        )
        comment = self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 2)
        comment = self.delete(
            f"/data/tasks/{task_id}/comments/{comment['id']}"
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 1)
        comment = self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 2)

    def test_retake_cap(self):
        task_id = str(self.task.id)
        asset_id = self.asset.id
        self.project.update({"max_retakes": 1})
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 1"},
        )
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.wip_status_id, "comment": "wip"},
        )
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
            400,
        )
        self.put(f"/data/entities/{asset_id}", {"data": {"max_retakes": 2}})
        self.get(f"/data/entities/{asset_id}")
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 2"},
        )
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.wip_status_id, "comment": "wip"},
        )
        self.post(
            f"/actions/tasks/{task_id}/comment",
            {"task_status_id": self.retake_status_id, "comment": "retake 3"},
            400,
        )

    def test_comment_many(self):
        project_id = str(self.project.id)
        task_id = str(self.task.id)
        self.generate_fixture_task(name="second_task")
        task2_id = str(self.task.id)
        path = f"/actions/projects/{project_id}/tasks/comment-many"
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
        self.get(f"data/tasks/{task_id}")
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 1)
        comments = self.get(f"data/tasks/{task_id}/comments")
        self.assertEqual(len(comments), 1)
        comments = self.get(f"data/tasks/{task2_id}/comments")
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
        path = f"/actions/projects/{project_id}/tasks/comment-many"
        self.assign_task_to_artist(task_id)
        self.post(path, new_comments)
        self.log_in_admin()
        self.get(f"data/tasks/{task_id}")
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["retake_count"], 1)
        comments = self.get(f"data/tasks/{task_id}/comments")
        self.assertEqual(len(comments), 1)
        comments = self.get(f"data/tasks/{task2_id}/comments")
        self.assertEqual(len(comments), 0)

    def test_attachments(self):
        self.delete_test_folder()
        self.create_test_folder()
        task_id = str(self.task.id)
        project_id = str(self.project.id)
        self.upload_file(
            f"/actions/tasks/{task_id}/comment",
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            extra_fields={
                "task_status_id": self.retake_status_id,
                "comment": "retake 1",
            },
        )
        attachment = self.get("data/attachment-files")[0]
        attachment = self.get(f"data/attachment-files/{attachment['id']}")
        path = f"/data/attachment-files/{attachment['id']}/file/th01.png"
        result_file_path = self.get_file_path("th01.png")

        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (180, 101))

        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        self.get(f"data/attachment-files/{attachment['id']}", 403)
        projects_service.add_team_member(project_id, self.user_vendor["id"])
        tasks_service.assign_task(task_id, self.user_vendor["id"])
        self.get(f"data/attachment-files/{attachment['id']}")
        self.delete_test_folder()
