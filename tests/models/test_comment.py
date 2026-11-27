from tests.base import ApiDBTestCase
from zou.app.models.comment import Comment


class CommentTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_assigned_task()
        self.comments = []
        self.comments.append(self.generate_fixture_comment())

    def test_repr(self):
        self.assertEqual(
            str(Comment.get(self.comments[0]["id"])),
            f"<Comment of {self.comments[0]['object_id']}>",
        )
