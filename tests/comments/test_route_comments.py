from tests.base import ApiDBTestCase

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.task import Task
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
        self.generate_fixture_user_client()
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
        self.assertEqual(result["task_status_id"], str(self.task_status.id))
        comments = tasks_service.get_comments(str(self.task.id))
        texts = [c["text"] for c in comments]
        self.assertIn("A new comment", texts)

    def test_comment_task_empty_text(self):
        result = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {"task_status_id": str(self.task_status.id)},
        )
        self.assertIsNotNone(result["id"])

    def test_get_comment_embeds_author(self):
        comment = self.get(f"/data/comments/{self.comment['id']}")
        self.assertEqual(comment["person"]["id"], comment["person_id"])
        self.assertEqual(comment["person"]["full_name"], "John Did")
        self.assertEqual(comment["person"]["role"], "admin")
        self.assertIn("has_avatar", comment["person"])

    def test_comments_list_embeds_author_full_name(self):
        comments = tasks_service.get_comments(str(self.task.id))
        self.assertEqual(comments[0]["person"]["full_name"], "John Did")
        self.assertEqual(comments[0]["person"]["role"], "admin")

    def test_get_comment_embeds_reply_author(self):
        comments_service.reply_comment(
            self.comment["id"], "My reply", person_id=str(self.user["id"])
        )
        comment = self.get(f"/data/comments/{self.comment['id']}")
        reply = comment["replies"][0]
        self.assertEqual(reply["person"]["id"], reply["person_id"])
        self.assertEqual(reply["person"]["full_name"], "John Did")

    def test_reply_comment_response_embeds_author(self):
        reply = self.post(
            f"/data/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/reply",
            {"text": "My reply"},
            200,
        )
        self.assertEqual(reply["person"]["id"], reply["person_id"])
        self.assertEqual(reply["person"]["full_name"], "John Did")

    def test_reply_author_hidden_from_client(self):
        """Studio members' identities must not be exposed to clients on
        replies, matching the comment author behavior."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )
        comments_service.reply_comment(
            comment["id"], "Studio reply", person_id=str(self.user["id"])
        )

        self.log_in_client()
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertIsNone(target["replies"][0]["person"])

    def test_comment_author_hidden_from_client_in_list(self):
        """The comment list must not embed a studio author for a client,
        matching the single-comment and reply author behavior, while the
        comment content stays visible."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )

        self.log_in_client()
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertTrue(target["for_client"])
        self.assertEqual(target["text"], "Visible to client")
        self.assertIsNone(target["person"])

    def test_client_author_embedded_for_client_in_list(self):
        """A client's own comment must keep its embedded author so it renders
        with a name and avatar."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()

        self.log_in_client()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Client question",
            },
        )
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(target["person"]["id"], str(client_person.id))
        self.assertEqual(target["person"]["role"], "client")

    def test_comment_author_hidden_from_client(self):
        """The single-comment endpoint must not embed a studio author for a
        client, matching the reply author behavior."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )

        self.log_in_client()
        result = self.get(f"/data/comments/{comment['id']}")
        self.assertEqual(result["text"], "Visible to client")
        self.assertIsNone(result["person"])

    def test_internal_comment_forbidden_for_client(self):
        """A client must not reach an internal studio comment (not for_client)
        on the single-comment endpoint. check_comment_access is the sole gate
        now that clean_get_result no longer blanks the text."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Internal only",
            },
        )

        self.log_in_client()
        self.get(f"/data/comments/{comment['id']}", 403)

    def test_editor_hidden_from_client_in_list(self):
        """A studio editor identity must not leak to clients in the comment
        list, matching the comment author behavior."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )
        comment_model = Comment.get(comment["id"])
        comment_model.editor_id = self.person.id
        comment_model.save()

        self.log_in_client()
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertIsNone(target["editor"])
        self.assertIsNone(target["editor_id"])

    def test_client_editor_kept_in_list(self):
        """A client editor stays visible, mirroring the author behavior."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )
        comment_model = Comment.get(comment["id"])
        comment_model.editor_id = client_person.id
        comment_model.save()

        self.log_in_client()
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        target = next(c for c in comments if c["id"] == comment["id"])
        self.assertEqual(target["editor"]["id"], str(client_person.id))
        self.assertEqual(target["editor"]["role"], "client")

    def test_editor_hidden_from_client(self):
        """The single-comment endpoint must not expose a studio editor to a
        client, matching the comment author behavior."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        comment = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Visible to client",
                "for_client": True,
            },
        )
        comment_model = Comment.get(comment["id"])
        comment_model.editor_id = self.person.id
        comment_model.save()

        self.log_in_client()
        result = self.get(f"/data/comments/{comment['id']}")
        self.assertIsNone(result["editor_id"])

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
        result = self.get(f"/data/projects/{self.project.id}/attachment-files")
        self.assertIsInstance(result, list)

    def test_get_task_attachment_files(self):
        result = self.get(f"/data/tasks/{self.task.id}/attachment-files")
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

    def test_comment_without_for_client_hidden_from_client(self):
        """A manager-authored comment without for_client stays hidden from
        clients (default behavior preserved)."""
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "Internal only",
            },
        )

        self.log_in_client()
        comments = tasks_service.get_comments(
            str(self.task.id), is_client=True
        )
        texts = [c["text"] for c in comments]
        self.assertNotIn("Internal only", texts)

    def test_for_client_default_false(self):
        result = self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": "default flag",
            },
        )
        self.assertFalse(result["for_client"])

    def _make_sibling_task(self):
        """Create a second task on the same asset with a different task type."""
        return Task.create(
            name="Modeling task",
            project_id=self.project.id,
            task_type_id=self.task_type_modeling.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

    def test_move_comment_between_tasks(self):
        sibling = self._make_sibling_task()
        original_created_at = self.comment["created_at"]
        original_status_id = self.comment["task_status_id"]
        result = self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/move",
            {"target_task_id": str(sibling.id)},
            200,
        )
        self.assertEqual(result["object_id"], str(sibling.id))
        self.assertEqual(result["created_at"], original_created_at)
        self.assertEqual(result["task_status_id"], original_status_id)

        source_comments = tasks_service.get_comments(str(self.task.id))
        target_comments = tasks_service.get_comments(str(sibling.id))
        self.assertNotIn(
            self.comment["id"], [c["id"] for c in source_comments]
        )
        self.assertIn(self.comment["id"], [c["id"] for c in target_comments])

    def test_move_comment_preserves_attachment(self):
        sibling = self._make_sibling_task()
        AttachmentFile.create(
            name="brief.pdf",
            size=0,
            extension="pdf",
            mimetype="application/pdf",
            comment_id=self.comment["id"],
        )
        self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/move",
            {"target_task_id": str(sibling.id)},
            200,
        )
        attachments = AttachmentFile.get_all_by(comment_id=self.comment["id"])
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].name, "brief.pdf")

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
        sibling = self._make_sibling_task()
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

    def test_move_comment_rejects_cross_entity(self):
        self.generate_fixture_asset(name="Tree2")
        other_asset_id = self.asset.id
        other_task = Task.create(
            name="Other entity task",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=other_asset_id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        response = self.app.post(
            f"/actions/tasks/{self.task_id}"
            f"/comments/{self.comment['id']}/move",
            data='{"target_task_id": "%s"}' % str(other_task.id),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_move_comment_rejects_same_task(self):
        response = self.app.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/move",
            data='{"target_task_id": "%s"}' % str(self.task.id),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_move_comment_rejects_mismatched_source_task(self):
        sibling = self._make_sibling_task()
        response = self.app.post(
            f"/actions/tasks/{sibling.id}"
            f"/comments/{self.comment['id']}/move",
            data='{"target_task_id": "%s"}' % str(sibling.id),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_move_comment_resets_task_status_on_both_tasks(self):
        self.generate_fixture_task_status_wip()
        sibling = self._make_sibling_task()
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

    def test_move_comment_rejects_non_manager(self):
        self.generate_fixture_user_cg_artist()
        sibling = self._make_sibling_task()
        self.log_in_cg_artist()
        response = self.app.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{self.comment['id']}/move",
            data='{"target_task_id": "%s"}' % str(sibling.id),
            headers=self.post_headers,
        )
        self.assertEqual(response.status_code, 403)
