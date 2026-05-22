from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment

from zou.app.utils import fields


class CommentTestCase(ApiDBTestCase):
    def setUp(self):
        super(CommentTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_assigned_task()
        self.generate_fixture_task_status_todo()
        self.comments = []
        self.comments.append(self.generate_fixture_comment())
        self.comments.append(self.generate_fixture_comment())
        self.comments.append(self.generate_fixture_comment())

    def test_repr(self):
        self.assertEqual(
            str(Comment.get(self.comments[0]["id"])),
            f"<Comment of {self.comments[0]['object_id']}>",
        )

    def test_get_comments(self):
        comments = self.get("data/comments")
        self.assertEqual(len(comments), 3)

    def test_get_comment(self):
        comment = self.get_first("data/comments?relations=true")
        comment_again = self.get(f"data/comments/{comment['id']}")
        # The single-comment endpoint embeds the author so guest commenters
        # render with a name and avatar; the list endpoint does not.
        person = comment_again.pop("person")
        self.assertEqual(person["id"], comment["person_id"])
        self.assertEqual(comment, comment_again)
        self.get_404(f"data/comments/{fields.gen_uuid()}/")

    def test_create_comment(self):
        data = {
            "object_type": "shot",
            "object_id": self.task.id,
            "person_id": self.person.id,
            "text": "New comment",
        }
        self.comment = self.post("data/comments", data)
        self.assertIsNotNone(self.comment["id"])

        comments = self.get("data/comments")
        self.assertEqual(len(comments), 4)

    def test_update_comment(self):
        comment = self.get_first("data/comments")
        data = {"text": "Edited comment"}
        self.put(f"data/comments/{comment['id']}", data)
        comment_again = self.get(f"data/comments/{comment['id']}")
        self.assertEqual(data["text"], comment_again["text"])
        comment_id = fields.gen_uuid()
        self.put_404(f"data/comments/{comment_id}", data)

    def test_delete_comment(self):
        comments = self.get("data/comments")
        self.assertEqual(len(comments), 3)
        comment = comments[0]
        self.delete(f"data/comments/{comment['id']}")
        comments = self.get("data/comments")
        self.assertEqual(len(comments), 2)
        self.delete_404(f"data/comments/{fields.gen_uuid()}")
