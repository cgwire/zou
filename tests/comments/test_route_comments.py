from tests.base import ApiDBTestCase

from zou.app.services import comments_service, tasks_service


class CommentRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(CommentRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "first comment",
        )

    def test_comment_task(self):
        result = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "A new comment",
            },
        )
        self.assertEqual(result["text"], "A new comment")
        self.assertEqual(
            result["task_status_id"], str(self.task_status.id)
        )
        comments = tasks_service.get_comments(str(self.task.id))
        texts = [c["text"] for c in comments]
        self.assertIn("A new comment", texts)

    def test_comment_task_empty_text(self):
        result = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {"task_status_id": str(self.task_status.id)},
        )
        self.assertIsNotNone(result["id"])

    def test_reply_comment(self):
        result = self.post(
            f"/data/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/reply",
            {"text": "My reply"},
            200,
        )
        self.assertIn("text", result)
        comment = tasks_service.get_comment(self.comment["id"])
        replies = comment.get("replies", [])
        reply_texts = [r["text"] for r in replies]
        self.assertIn("My reply", reply_texts)

    def test_delete_reply_comment(self):
        reply = comments_service.reply_comment(
            self.comment["id"],
            "Reply to delete",
            person_id=str(self.user["id"]),
        )
        reply_id = reply["id"]
        self.delete(
            f"/data/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/reply/{reply_id}",
            200,
        )
        comment = tasks_service.get_comment(self.comment["id"])
        reply_ids = [r["id"] for r in comment.get("replies", [])]
        self.assertNotIn(reply_id, reply_ids)

    def test_get_project_attachment_files(self):
        result = self.get(
            f"/data/projects/{self.project.id}/attachment-files"
        )
        self.assertIsInstance(result, list)

    def test_get_task_attachment_files(self):
        result = self.get(
            f"/data/tasks/{self.task.id}/attachment-files"
        )
        self.assertIsInstance(result, list)

    def test_comment_many_tasks(self):
        result = self.post(
            f"/actions/projects/{self.project.id}/tasks/comment-many",
            [
                {
                    "object_id": str(self.task.id),
                    "task_status_id": str(self.task_status.id),
                    "comment": "Batch comment",
                }
            ],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "Batch comment")
        comments = tasks_service.get_comments(str(self.task.id))
        texts = [c["text"] for c in comments]
        self.assertIn("Batch comment", texts)
