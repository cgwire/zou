from tests.blueprints.comments.base import CommentTestCase, MentionTestCase
from zou.app.services import comments_service


class BatchCommentTestCase(CommentTestCase):
    """
    Posting several comments in one request, on one task or on many.
    """

    def test_batch_comment_task(self):
        comments = [
            {"task_status_id": str(self.task_status.id), "text": "note 1"},
            {"task_status_id": str(self.task_status.id), "text": "note 2"},
        ]
        result = self.post(
            f"/actions/tasks/{self.task.id}/batch-comment",
            {"comments": comments},
        )
        self.assertEqual(len(result), 2)
        texts = [
            c["text"] for c in comments_service.get_comments(self.task.id)
        ]
        self.assertIn("note 1", texts)
        self.assertIn("note 2", texts)

    def test_batch_comment_tasks(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        comments = [
            {
                "task_id": str(self.task.id),
                "task_status_id": str(self.task_status.id),
                "text": "asset note",
            },
            {
                "task_id": str(self.shot_task.id),
                "task_status_id": str(self.task_status.id),
                "text": "shot note",
            },
        ]
        result = self.post(
            "/actions/tasks/batch-comment", {"comments": comments}
        )
        self.assertEqual(len(result), 2)
        asset_texts = [
            c["text"] for c in comments_service.get_comments(self.task.id)
        ]
        shot_texts = [
            c["text"] for c in comments_service.get_comments(self.shot_task.id)
        ]
        self.assertIn("asset note", asset_texts)
        self.assertIn("shot note", shot_texts)


class MentionedArtistPreviewTestCase(MentionTestCase):
    def test_mentioned_artist_cannot_add_preview(self):
        comment = self.mention_artist()
        self.log_in_cg_artist()
        self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{comment['id']}/add-preview",
            {"revision": 1},
            403,
        )
