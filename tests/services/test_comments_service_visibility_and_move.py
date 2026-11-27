from tests.blueprints.comments.base import (
    ClientCommentTestCase,
    CommentTestCase,
)
from zou.app.models.comment import Comment
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.services import comments_service, tasks_service


class ClientCommentReadTestCase(ClientCommentTestCase):
    """
    What get_comments gives a client of a comment: its author, its editor
    and the authors of its replies.
    """

    def test_comments_list_embeds_author_full_name(self):
        comments = comments_service.get_comments(str(self.task.id))
        self.assertEqual(comments[0]["person"]["full_name"], "John Did")
        self.assertEqual(comments[0]["person"]["role"], "admin")

    def test_reply_author_shown_to_client(self):
        """
        A studio replier is named to the client, like the comment author.
        """
        self.put_the_client_in_the_team()
        comment = self.comment_for_client()
        comments_service.reply_comment(
            comment["id"], "Studio reply", person_id=str(self.user["id"])
        )

        self.log_in_client()
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        replier = target["replies"][0]["person"]
        self.assertEqual(replier["id"], str(self.user["id"]))
        self.assertEqual(replier["full_name"], "John Did")

    def test_comment_author_shown_to_client_in_list(self):
        """
        The comment list embeds a studio author for a client too.
        """
        self.put_the_client_in_the_team()
        comment = self.comment_for_client()

        self.log_in_client()
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertTrue(target["for_client"])
        self.assertEqual(target["text"], "Visible to client")
        self.assertEqual(target["person"]["id"], str(self.user["id"]))
        self.assertEqual(target["person"]["full_name"], "John Did")

    def test_client_author_embedded_for_client_in_list(self):
        """
        A client's own comment must keep its embedded author so it renders
        with a name and avatar.
        """
        client_id = str(self.put_the_client_in_the_team().id)

        self.log_in_client()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Client question",
            },
        )
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(target["person"]["id"], client_id)
        self.assertEqual(target["person"]["role"], "client")

    def test_editor_shown_to_client_in_list(self):
        """
        A studio editor stays in the comment list of a client, like the
        author.
        """
        self.put_the_client_in_the_team()
        comment = self.comment_for_client()
        comment_model = Comment.get(comment["id"])
        comment_model.editor_id = self.person.id
        comment_model.save()

        self.log_in_client()
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(target["editor"]["id"], str(self.person.id))
        self.assertEqual(target["editor_id"], str(self.person.id))

    def test_client_editor_kept_in_list(self):
        """
        A client editor stays visible, mirroring the author behavior.
        """
        client_id = str(self.put_the_client_in_the_team().id)
        comment = self.comment_for_client()
        comment_model = Comment.get(comment["id"])
        comment_model.editor_id = client_id
        comment_model.save()

        self.log_in_client()
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(target["editor"]["id"], client_id)
        self.assertEqual(target["editor"]["role"], "client")

    def test_comment_without_for_client_hidden_from_client(self):
        """
        A manager-authored comment without for_client stays hidden from
        clients (default behavior preserved).
        """
        self.put_the_client_in_the_team()
        self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Internal only",
            },
        )

        self.log_in_client()
        comments = comments_service.get_comments(
            str(self.task.id), is_client=True
        )
        texts = [c["text"] for c in comments]
        self.assertNotIn("Internal only", texts)


class MoveCommentFollowersTestCase(CommentTestCase):
    """
    The notifications and the task statuses that follow a moved comment.
    """

    def test_move_comment_rebuilds_notifications(self):
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        cg_person = Person.get(self.user_cg_artist["id"])
        self.project.team = [
            cg_person,
            self.person,
            Person.get(self.user["id"]),
        ]
        self.project.save()
        sibling = self.make_sibling_task()
        sibling.assignees = [cg_person]
        sibling.save()

        Notification.delete_all_by(comment_id=self.comment["id"])
        Notification.create(
            person_id=self.person.id,
            author_id=self.user["id"],
            comment_id=self.comment["id"],
            task_id=self.task.id,
            type="comment",
        )
        self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/move",
            {"target_task_id": str(sibling.id)},
            200,
        )
        notifications = Notification.get_all_by(comment_id=self.comment["id"])
        recipient_ids = {str(n.person_id) for n in notifications}
        task_ids = {str(n.task_id) for n in notifications}
        self.assertIn(self.user_cg_artist["id"], recipient_ids)
        self.assertEqual(task_ids, {str(sibling.id)})

    def test_move_comment_resets_task_status_on_both_tasks(self):
        self.generate_fixture_task_status_wip()
        sibling = self.make_sibling_task()
        source_initial_status = self.task.task_status_id
        wip_comment = comments_service.new_comment(
            self.task.id,
            self.task_status_wip.id,
            self.user["id"],
            "wip note posted on the wrong task",
        )
        self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{wip_comment['id']}/move",
            {"target_task_id": str(sibling.id)},
            200,
        )
        source_after = tasks_service.get_task(str(self.task.id))
        target_after = tasks_service.get_task(str(sibling.id))
        self.assertEqual(
            source_after["task_status_id"], str(source_initial_status)
        )
        self.assertEqual(
            target_after["task_status_id"], str(self.task_status_wip.id)
        )
