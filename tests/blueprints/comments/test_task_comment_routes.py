from tests.blueprints.tasks.test_tasks import TaskTestCase
from zou.app.services import (
    news_service,
    notifications_service,
    persons_service,
)
from zou.app.utils import fields


class TaskCommentTestCase(TaskTestCase):
    """
    Commenting through the task routes, and what a comment does to the
    task it lands on: its status, its retake count and its dates.
    """

    def test_comment_task(self):
        self.project_id = self.project.id
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        user_cg_artist = persons_service.get_person_raw(
            self.user_cg_artist["id"]
        )
        user_manager = persons_service.get_person_raw(self.user_manager["id"])
        self.project.team = [self.person, user_cg_artist, user_manager]
        self.project.save()
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        comment = self.post(path, data)
        self.assertEqual(comment["text"], data["comment"])
        self.assertEqual(
            comment["person"]["first_name"], self.user["first_name"]
        )
        self.assertEqual(comment["task_status"]["short_name"], "wip")

        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_status_id"], str(self.wip_status_id))
        self.assertIsNotNone(tasks[0]["last_comment_date"])

        comments = self.get("/data/comments/")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["text"], data["comment"])
        self.assertEqual(comments[0]["person_id"], self.user["id"])

        notifications = notifications_service.get_recent_notifications(
            "comment"
        )
        self.assertEqual(len(notifications), 1)
        notifications = notifications_service.get_recent_notifications(
            "mention"
        )
        self.assertEqual(notifications, [])

        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test @John Did2",
        }
        comment = self.post(path, data)
        notifications = notifications_service.get_recent_notifications(
            "comment"
        )
        self.assertEqual(len(notifications), 2)
        notifications = notifications_service.get_recent_notifications(
            "mention"
        )
        self.assertEqual(len(notifications), 1)

        news_list = news_service.get_last_news_for_project(
            news_service.NewsFilters(project_id=self.project_id)
        )
        self.assertEqual(len(news_list["data"]), 2)

    def test_edit_comment(self):
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()

        user = persons_service.get_person_raw(self.user["id"])
        user_cg_artist = persons_service.get_person_raw(
            self.user_cg_artist["id"]
        )
        user_manager = persons_service.get_person_raw(self.user_manager["id"])

        self.project.team = [self.person, user, user_cg_artist, user_manager]
        self.project.save()
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test @John Doe",
        }
        comment = self.post(path, data)
        notifications = notifications_service.get_recent_notifications(
            "mention"
        )
        self.assertEqual(len(notifications), 1)

        path = f"/data/comments/{comment['id']}"
        data = {"text": "comment test @John Did2 @John Did3"}
        comment = self.put(path, data)
        notifications = notifications_service.get_recent_notifications(
            "mention"
        )
        self.assertEqual(len(notifications), 2)

    def test_comment_task_with_retake(self):
        self.generate_fixture_task()
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {
            "task_status_id": self.retake_status_id,
            "comment": "retake test",
        }
        data_wip = {
            "task_status_id": self.wip_status_id,
            "comment": "wip test",
        }
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data_wip)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 1)
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertEqual(tasks[0]["retake_count"], 2)

    def test_comment_task_with_wip(self):
        self.generate_fixture_task()
        self.task.update({"real_start_date": None})
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {"task_status_id": self.wip_status_id, "comment": "wip test"}
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertIsNotNone(tasks[0]["real_start_date"])

    def test_comment_task_with_done(self):
        self.generate_fixture_task()
        self.task.update({"end_date": None})
        path = f"/actions/tasks/{self.task.id}/comment/"
        data = {"task_status_id": self.wfa_status_id, "comment": "wip test"}
        self.post(path, data)
        tasks = self.get("/data/tasks")
        self.assertIsNotNone(tasks[0]["end_date"])

    def test_task_comments(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.task_2_id = str(self.task_standard.id)

        path = f"/actions/tasks/{self.task_id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        self.post(path, data)
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test 2",
        }
        self.post(path, data)

        path = f"/actions/tasks/{self.task_2_id}/comment/"
        self.post(path, data)

        path = f"/data/tasks/{self.task_id}/comments/"
        comments = self.get(path)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["text"], data["comment"])
        self.assertEqual(
            comments[0]["person"]["first_name"], self.user["first_name"]
        )
        self.assertEqual(comments[0]["task_status"]["short_name"], "wip")

        self.get(f"/data/tasks/{fields.gen_uuid()}/comments", 404)

    def test_delete_task_comment(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)

        path = f"/actions/tasks/{self.task_id}/comment/"
        data = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test",
        }
        self.post(path, data)
        comment = {
            "task_status_id": self.wip_status_id,
            "comment": "comment test 2",
        }
        comment = self.post(path, comment)

        other_task_path = (
            f"/data/tasks/{fields.gen_uuid()}/comments/{comment['id']}"
        )
        self.delete(other_task_path, 404)
        path = f"/data/tasks/{self.task_id}/comments/{comment['id']}"
        comments = self.delete(path)
        self.delete(path, 404)
        path = f"/data/tasks/{self.task_id}/comments/"
        comments = self.get(path)
        self.assertEqual(len(comments), 1)
