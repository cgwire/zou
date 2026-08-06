import io
import os

from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.attachment_file import AttachmentFile

from zou.app.services import (
    comments_service,
    entities_service,
    persons_service,
    tasks_service,
    exception,
)
from zou.app.utils import fields


class CommentsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.project.update({"max_retakes": 3})
        self.project.save()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.generate_fixture_person()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize(relations=True)
        self.person_id = str(self.person.id)
        self.person_dict = self.generate_fixture_person(
            first_name="Jane", email="jane.doe@gmail.com"
        ).serialize()
        self.wfa_status = self.generate_fixture_task_status_wfa()
        self.project_id = str(self.project.id)

    def test_new_comment(self):
        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )
        self.assertIsNotNone(self.comment["id"])
        self.assertIsNotNone(self.comment["created_at"])
        self.assertEqual(self.comment["object_id"], str(self.task.id))
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "second comment",
            created_at="2024-01-23 10:00:00",
        )
        self.assertEqual(self.comment["created_at"], "2024-01-23T10:00:00")

    def test_new_comment_with_attachments(self):
        """
        The files a comment is posted with land on it, under the comment
        that carries them.

        Two of the same name are kept as they are: attachment_file has no
        unique constraint, so the IntegrityError branch that would add a
        random suffix never fires. chats_service randomizes up front rather
        than relying on it.
        """
        comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "with a file",
            files={
                "file-0": self.uploaded_file("notes.txt"),
                "file-1": self.uploaded_file("brief.pdf"),
            },
        )

        attachments = sorted(
            comment["attachment_files"], key=lambda a: a["name"]
        )
        self.assertEqual(
            [(a["name"], a["extension"]) for a in attachments],
            [("brief.pdf", "pdf"), ("notes.txt", "txt")],
        )
        self.assertEqual(
            {
                str(row.comment_id)
                for row in AttachmentFile.get_all_by(comment_id=comment["id"])
            },
            {comment["id"]},
        )

    def test_check_retake_capping(self):
        self.project.update({"max_retakes": 2})
        retake_status = self.generate_fixture_task_status_retake().serialize()
        task = self.task.serialize()
        comments_service._check_retake_capping(retake_status, task)
        self.task.update({"retake_count": 3})
        task = self.task.serialize()
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(retake_status, task)

        self.shot.update({"data": {"max_retakes": 4}})
        self.shot.save()
        entities_service.clear_entity_cache(task["entity_id"])
        comments_service._check_retake_capping(retake_status, task)
        self.task.update({"retake_count": 5})
        task = self.task.serialize()
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(retake_status, task)

    def test_get_comment_author(self):
        user_id = self.user["id"]
        author = comments_service._get_comment_author(self.user["id"])
        self.assertEqual(author["id"], user_id)

    def test_manage_status_change(self):
        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "first comment"
        )
        task_status = self.task_status.serialize()
        retake_status = self.generate_fixture_task_status_retake().serialize()
        task = self.task.serialize()
        comment = self.comment
        task, status_changed = comments_service._manage_status_change(
            task_status, task, comment
        )
        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 0)
        task, status_changed = comments_service._manage_status_change(
            retake_status, task, comment
        )
        self.assertTrue(status_changed)
        self.assertEqual(task["retake_count"], 1)

        old_comment = comments_service.new_comment(
            self.task.id,
            retake_status["id"],
            self.user["id"],
            "old comment",
            created_at="1999-12-23 10:00:00",
        )
        task, status_changed = comments_service._manage_status_change(
            retake_status, task, old_comment
        )

        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 1)

        task, status_changed = comments_service._manage_status_change(
            self.wfa_status, task, comment
        )
        self.assertIsNotNone(task["end_date"])

    def test_manage_status_change_emits_to_review(self):
        """
        Moving a task to a feedback-request status via a comment must
        re-emit the legacy task:to-review event so existing gazu listeners
        keep working after the deprecation of /actions/tasks/<id>/to-review.
        """
        fired_events = self.capture_events("task:to-review")

        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "to wfa"
        )
        task = self.task.serialize()

        comments_service._manage_status_change(self.wfa_status, task, comment)

        self.assertEqual(len(fired_events), 1)
        payload = fired_events[0]
        self.assertEqual(payload["task_id"], str(self.task.id))
        self.assertEqual(payload["new_task_status_id"], self.wfa_status["id"])
        self.assertEqual(payload["comment_id"], comment["id"])

    def uploaded_file(self, filename):
        return FileStorage(
            stream=io.BytesIO(b"attachment content"), filename=filename
        )

    def _create_attachment(self, comment, filename):
        return comments_service.create_attachment(
            comment, self.uploaded_file(filename)
        )

    def test_create_attachment(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        attachment = self._create_attachment(comment, "notes.txt")
        self.assertEqual(attachment["name"], "notes.txt")
        self.assertEqual(attachment["extension"], "txt")
        self.assertGreater(attachment["size"], 0)

    def test_is_inline_safe_mimetype(self):
        for mimetype in [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "IMAGE/PNG",
            "image/jpeg; charset=binary",
        ]:
            self.assertTrue(
                comments_service.is_inline_safe_mimetype(mimetype), mimetype
            )
        for mimetype in [
            "image/svg+xml",
            "text/html",
            "application/pdf",
            "application/octet-stream",
            "",
            None,
        ]:
            self.assertFalse(
                comments_service.is_inline_safe_mimetype(mimetype), mimetype
            )

    def test_create_attachment_failure_cleans_up(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        uploaded_file = FileStorage(
            stream=io.BytesIO(b"attachment content"), filename="notes.txt"
        )
        os.makedirs(config.TMP_DIR, exist_ok=True)
        tmp_files_before = set(os.listdir(config.TMP_DIR))

        with patch(
            "zou.app.services.comments_service.file_store.add_file",
            side_effect=OSError("storage down"),
        ):
            with self.assertRaises(OSError):
                comments_service.create_attachment(comment, uploaded_file)

        self.assertEqual(AttachmentFile.query.count(), 0)
        self.assertEqual(set(os.listdir(config.TMP_DIR)), tmp_files_before)

    def test_get_attachment_file_path(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        attachment = self._create_attachment(comment, "notes.txt")
        path = comments_service.get_attachment_file_path(attachment)
        with open(path, "rb") as attachment_file:
            self.assertEqual(attachment_file.read(), b"attachment content")

    def assert_the_attachment_listing_is_scoped(self, list_files, scope_id):
        """
        The listing carries the attachments of the thing it is asked about,
        and answers empty for an id that owns none.
        """
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        attachment = self._create_attachment(comment, "notes.txt")

        attachments = list_files(scope_id)

        self.assertEqual(
            [attached["id"] for attached in attachments], [attachment["id"]]
        )
        self.assertEqual(list_files(fields.gen_uuid()), [])

    def test_get_all_attachment_files_for_project(self):
        self.assert_the_attachment_listing_is_scoped(
            comments_service.get_all_attachment_files_for_project,
            self.project_id,
        )

    def test_get_all_attachment_files_for_task(self):
        self.assert_the_attachment_listing_is_scoped(
            comments_service.get_all_attachment_files_for_task,
            str(self.task.id),
        )

    def test_reply_comment(self):
        reply_text = "first reply"
        comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "comment that starts a thread discussion",
        )
        comments_service.reply_comment(
            comment["id"], reply_text, person_id=self.user["id"]
        )
        comment = tasks_service.get_comment(comment["id"])
        self.assertEqual(len(comment["replies"]), 1)
        self.assertEqual(comment["replies"][0]["text"], reply_text)
        self.assertEqual(comment["replies"][0]["person_id"], self.user["id"])
        comments_service.reply_comment(
            comment["id"],
            "mention @Animation and @John Doe",
            person_id=self.user["id"],
        )
        tasks_service.clear_comment_cache(comment["id"])
        comment = tasks_service.get_comment(comment["id"])
        self.assertEqual(len(comment["replies"]), 2)
        self.assertListEqual(
            comment["replies"][1]["mentions"], [self.person_id]
        )
        self.assertListEqual(
            comment["replies"][1]["department_mentions"],
            [str(self.department_animation.id)],
        )

    def test_acknowledge_comment(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "to ack"
        )
        path = f"data/tasks/{self.task.id}/comments/{comment['id']}/ack"
        result = self.post(path, {}, 200)
        self.assertIn(self.user["id"], result["acknowledgements"])
        result = self.post(path, {}, 200)
        self.assertEqual(result["acknowledgements"], [])

    def test_get_reply(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        found = comments_service.get_reply(comment["id"], reply["id"])
        self.assertEqual(found["text"], "the reply")
        self.assertRaises(
            exception.ReplyNotFoundException,
            comments_service.get_reply,
            comment["id"],
            fields.gen_uuid(),
        )

    def test_delete_reply_takes_its_attachments_with_it(self):
        """
        A reply carries its own attachments, and they go with it. The
        comment's own attachments stay.
        """
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        comments_service.add_attachments_to_comment(
            comment, {"file": self.uploaded_file("kept.txt")}
        )
        comments_service.add_attachments_to_comment(
            tasks_service.get_comment(comment["id"]),
            {"file": self.uploaded_file("gone.txt")},
            reply_id=reply["id"],
        )

        comments_service.delete_reply(comment["id"], reply["id"])

        self.assertEqual(
            [
                attachment.name
                for attachment in AttachmentFile.get_all_by(
                    comment_id=comment["id"]
                )
            ],
            ["kept.txt"],
        )

    def test_delete_reply(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "comment"
        )
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        comments_service.delete_reply(comment["id"], reply["id"])
        self.assertRaises(
            exception.ReplyNotFoundException,
            comments_service.get_reply,
            comment["id"],
            reply["id"],
        )

    def test_reset_mentions(self):
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "mentions @Animation @John Doe",
        )
        comment = comments_service.reset_mentions(self.comment)
        self.assertListEqual(comment["mentions"], [self.person_id])
        self.assertListEqual(
            comment["department_mentions"], [str(self.department_animation.id)]
        )

    def test_get_comment_mentions(self):
        mentions = comments_service.get_comment_mentions(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_mentions(
            self.project_id,
            "mention @John Doe",
        )
        person = persons_service.get_person_raw(self.person_id)
        self.assertListEqual(mentions, [person])

    def test_get_comment_mention_ids(self):
        mentions = comments_service.get_comment_mention_ids(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_mention_ids(
            self.project_id,
            "mention @John Doe",
        )
        self.assertListEqual(mentions, [self.person_id])

    def test_get_comment_department_mentions(self):
        mentions = comments_service.get_comment_department_mentions(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_department_mentions(
            self.project_id,
            "mention @Animation",
        )
        self.assertListEqual(mentions, [self.department_animation])

    def test_get_comment_department_mention_ids(self):
        mentions = comments_service.get_comment_department_mention_ids(
            self.project_id,
            "nothing to mention",
        )
        self.assertListEqual(mentions, [])
        mentions = comments_service.get_comment_department_mention_ids(
            self.project_id,
            "mention @Animation",
        )
        self.assertListEqual(mentions, [str(self.department_animation.id)])

    def test_get_comment_hashtags(self):
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #animation"
        )
        self.assertListEqual(hashtags, ["animation"])

        hashtags = comments_service.get_comment_hashtags(
            "Check this out #animation #lighting"
        )
        self.assertIn("animation", hashtags)
        self.assertIn("lighting", hashtags)

        hashtags = comments_service.get_comment_hashtags(
            "Great work! #ANIMATION"
        )
        self.assertListEqual(hashtags, ["animation"])

        hashtags = comments_service.get_comment_hashtags(
            "Great work! #animation."
        )
        self.assertListEqual(hashtags, ["animation"])

        hashtags = comments_service.get_comment_hashtags(
            "Great work! No hashtags here"
        )
        self.assertListEqual(hashtags, [])

    def test_get_comment_hashtags_all_priority(self):
        hashtags = comments_service.get_comment_hashtags(
            "Great work! #all #animation #lighting"
        )
        self.assertListEqual(hashtags, ["all"])

        hashtags = comments_service.get_comment_hashtags("Great work! #all")
        self.assertListEqual(hashtags, ["all"])

    def test_filter_tasks_by_hashtags(self):
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
            {"id": "4", "task_type_name": "rigging"},
        ]
        task_type_animation = {"id": "tt1", "name": "Animation"}

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["modeling"], task_type_animation
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["task_type_name"], "modeling")

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["modeling", "lighting"], task_type_animation
        )
        self.assertEqual(len(filtered), 2)
        task_types = [task["task_type_name"] for task in filtered]
        self.assertIn("modeling", task_types)
        self.assertIn("lighting", task_types)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["animation", "modeling"], task_type_animation
        )
        self.assertEqual(len(filtered), 1)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, ["all"], task_type_animation
        )
        self.assertEqual(len(filtered), 3)

        filtered = comments_service.filter_tasks_by_hashtags(
            tasks, [], task_type_animation
        )
        self.assertEqual(filtered, [])

    def test_create_comment_with_hashtags(self):
        """
        Integration test for create_comment with hashtag functionality
        """
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )

        # A distinct status on the siblings, so that "the propagated comment
        # keeps the target's own status" is a statement that can fail.
        sibling_status_id = str(self.wfa_status["id"])
        for sibling in [modeling_task, concept_task]:
            sibling.update({"task_status_id": sibling_status_id})

        comment_text = "Great shot! Please check #modeling #concept"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)

        for sibling in [modeling_task, concept_task]:
            comments = tasks_service.get_comments(sibling.id)
            self.assertEqual(len(comments), 1)
            self.assertIn("Animation", comments[0]["text"])
            # _handle_hashtags reposts with the target's current status, not
            # with the one the author picked, so the sibling does not move.
            self.assertEqual(comments[0]["task_status_id"], sibling_status_id)
            self.assertEqual(
                str(tasks_service.get_task_raw(sibling.id).task_status_id),
                sibling_status_id,
            )
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
            with_hashtags=False,
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)

    def test_create_comment_with_all_hashtag(self):
        self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )

        comment_text = "Important update for everyone #all"
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text=comment_text,
        )
        self.assertIsNotNone(comment["id"])
        self.assertEqual(comment["text"], comment_text)
        self.assertEqual(comment["person_id"], self.person_id)
