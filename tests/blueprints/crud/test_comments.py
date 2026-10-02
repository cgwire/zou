from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.services import projects_service, tasks_service

from zou.app.utils import fields


class CommentTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_assigned_task()
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

    def log_in_team_artist(self):
        # A team member who wrote none of the comments.
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()

    def test_unassigned_artist_cannot_change_a_checklist(self):
        checklist = [{"text": "Fix the hands", "checked": False}]
        comment_id = self.comments[0]["id"]
        Comment.get(comment_id).update({"checklist": checklist})
        self.log_in_team_artist()
        # Sent unchanged, the checklist goes through: the refusals below
        # come from the checklist rule, not from the project check.
        self.put(f"data/comments/{comment_id}", {"checklist": checklist})
        for change in (
            [{"text": "Fix the hands", "checked": True}],
            [{"text": "Looks good", "checked": True}],
            checklist + [{"text": "And the feet", "checked": False}],
            [],
        ):
            self.put(f"data/comments/{comment_id}", {"checklist": change}, 403)
        self.assertEqual(Comment.get(comment_id).checklist, checklist)

    def log_in_team_client(self):
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project.id, self.user_client["id"]
        )
        self.log_in_client()

    def test_client_cannot_change_a_checklist(self):
        comment_id = self.comments[0]["id"]
        # A comment the client reads, so the refusal below comes from the
        # checklist rule.
        Comment.get(comment_id).update({"for_client": True})
        self.log_in_team_client()
        self.put(f"data/comments/{comment_id}", {"checklist": []})
        self.put(
            f"data/comments/{comment_id}",
            {"checklist": [{"text": "Looks good", "checked": True}]},
            403,
        )

    def test_client_cannot_update_a_comment_it_cannot_read(self):
        comment_id = self.comments[0]["id"]
        self.log_in_team_client()
        # Even an empty change answered with the internal comment, and made
        # the client its editor.
        self.put(f"data/comments/{comment_id}", {}, 403)
        self.assertIsNone(Comment.get(comment_id).editor_id)

    def test_update_null_checklist_as_unassigned_artist(self):
        comment_id = self.comments[0]["id"]
        self.log_in_team_artist()
        self.put(f"data/comments/{comment_id}", {"checklist": []})
        Comment.get(comment_id).update({"checklist": None})
        self.put(f"data/comments/{comment_id}", {"checklist": []}, 403)

    def test_assigned_artist_can_tick_a_checklist(self):
        comment_id = self.comments[0]["id"]
        Comment.get(comment_id).update(
            {"checklist": [{"text": "Fix the hands", "checked": False}]}
        )
        self.generate_fixture_user_cg_artist()
        tasks_service.assign_task(str(self.task.id), self.user_cg_artist["id"])
        self.log_in_team_artist()
        ticked = [{"text": "Fix the hands", "checked": True}]
        self.put(f"data/comments/{comment_id}", {"checklist": ticked})
        self.assertEqual(Comment.get(comment_id).checklist, ticked)

    def test_delete_comment(self):
        comments = self.get("data/comments")
        self.assertEqual(len(comments), 3)
        comment = comments[0]
        self.delete(f"data/comments/{comment['id']}")
        comments = self.get("data/comments")
        self.assertEqual(len(comments), 2)
        self.delete_404(f"data/comments/{fields.gen_uuid()}")
