import io
import os

from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.news import News
from zou.app.models.notification import Notification

from zou.app.services import (
    comments_service,
    concepts_service,
    entities_service,
    exception,
    persons_service,
    tasks_service,
)
from zou.app.utils import fields


class CommentsTestCase(ApiDBTestCase):
    """
    One shot with an animation task, two people, and a production capping
    retakes: the context every comment of this service is posted in.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.project.update({"max_retakes": 3})
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.person_id = str(self.person.id)
        self.person_dict = self.generate_fixture_person(
            first_name="Jane", email="jane.doe@gmail.com"
        ).serialize()
        self.wfa_status = self.generate_fixture_task_status_wfa()
        self.project_id = str(self.project.id)

    def comment(self, text="a comment", **kwargs):
        return comments_service.new_comment(
            kwargs.pop("task_id", self.task.id),
            kwargs.pop("task_status_id", self.task_status.id),
            kwargs.pop("person_id", self.user["id"]),
            text,
            **kwargs,
        )

    def uploaded_file(self, filename):
        return FileStorage(
            stream=io.BytesIO(b"attachment content"), filename=filename
        )


class NewCommentTestCase(CommentsTestCase):
    """
    The row itself: what lands in the database and what is announced.
    """

    def test_a_comment_is_tied_to_its_task(self):
        comment = self.comment("first comment")
        self.assertIsNotNone(comment["id"])
        self.assertIsNotNone(comment["created_at"])
        self.assertEqual(comment["object_id"], str(self.task.id))
        self.assertEqual(comment["object_type"], "Task")

    def test_a_comment_is_announced(self):
        captured = self.capture_events("comment:new")
        comment = self.comment()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["comment_id"], comment["id"])
        self.assertEqual(captured[0]["task_id"], str(self.task.id))
        self.assertEqual(
            captured[0]["task_status_id"], str(self.task_status.id)
        )

    def test_a_date_can_be_forced_on_an_imported_comment(self):
        """
        Two formats are accepted, and a date that reads as neither is
        dropped rather than refused: an import must not fail on one row.
        """
        for created_at, expected in [
            ("2024-01-23 10:00:00", "2024-01-23T10:00:00"),
            ("2024-01-23T10:00:00", "2024-01-23T10:00:00"),
        ]:
            with self.subTest(created_at=created_at):
                comment = self.comment("dated", created_at=created_at)
                self.assertEqual(comment["created_at"], expected)

        comment = self.comment("undated", created_at="not a date")
        self.assertIsNotNone(comment["created_at"])

    def test_the_mentions_are_read_off_the_text(self):
        comment = self.comment("mentions @Animation and @John Doe")
        self.assertEqual(comment["mentions"], [self.person_id])
        self.assertEqual(
            comment["department_mentions"],
            [str(self.department_animation.id)],
        )

    def test_the_files_a_comment_is_posted_with_land_on_it(self):
        """
        Two of the same name are kept as they are: attachment_file has no
        unique constraint, so the IntegrityError branch that would add a
        random suffix never fires. chats_service randomizes up front rather
        than relying on it.
        """
        comment = self.comment(
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

    def test_the_author_is_the_person_the_comment_names(self):
        self.assertEqual(
            comments_service._get_comment_author(self.person_id)["id"],
            self.person_id,
        )


class StatusChangeTestCase(CommentsTestCase):
    """
    What a comment does to the task it is posted on.
    """

    def test_a_comment_keeping_the_status_changes_nothing(self):
        comment = self.comment()
        task, status_changed = comments_service._manage_status_change(
            self.task_status.serialize(), self.task.serialize(), comment
        )
        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 0)

    def test_a_retake_counts(self):
        retake_status = self.generate_fixture_task_status_retake().serialize()
        comment = self.comment()
        task, status_changed = comments_service._manage_status_change(
            retake_status, self.task.serialize(), comment
        )
        self.assertTrue(status_changed)
        self.assertEqual(task["retake_count"], 1)

    def test_a_status_asking_for_feedback_closes_the_task(self):
        comment = self.comment()
        task, _ = comments_service._manage_status_change(
            self.wfa_status, self.task.serialize(), comment
        )
        self.assertIsNotNone(task["end_date"])

    def test_a_status_starting_the_work_stamps_it(self):
        wip_status = self.generate_fixture_task_status_wip().serialize()
        comment = self.comment()
        task, _ = comments_service._manage_status_change(
            wip_status, self.task.serialize(), comment
        )
        self.assertIsNotNone(task["real_start_date"])

    def test_a_comment_older_than_the_last_one_does_not_move_the_task(self):
        """
        Importing an old comment must not rewind a task: the whole history
        is replayed instead.
        """
        retake_status = self.generate_fixture_task_status_retake().serialize()
        comment = self.comment()
        task, _ = comments_service._manage_status_change(
            retake_status, self.task.serialize(), comment
        )
        old_comment = self.comment(
            "old comment",
            task_status_id=retake_status["id"],
            created_at="1999-12-23 10:00:00",
        )

        task, status_changed = comments_service._manage_status_change(
            retake_status, task, old_comment
        )

        self.assertFalse(status_changed)
        self.assertEqual(task["retake_count"], 1)

    def test_a_status_change_is_announced(self):
        captured = self.capture_events("task:status-changed")
        comment = self.comment()
        comments_service._manage_status_change(
            self.wfa_status, self.task.serialize(), comment
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(
            captured[0]["new_task_status_id"], self.wfa_status["id"]
        )

    def test_a_task_sent_to_review_still_announces_the_old_event(self):
        """
        The legacy /actions/tasks/<id>/to-review route emitted
        task:to-review; Kitsu now posts a comment instead, so the event is
        re-emitted from here to keep the gazu listeners working.
        """
        captured = self.capture_events("task:to-review")

        comment = self.comment("to wfa")
        comments_service._manage_status_change(
            self.wfa_status, self.task.serialize(), comment
        )

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["task_id"], str(self.task.id))
        self.assertEqual(
            captured[0]["new_task_status_id"], self.wfa_status["id"]
        )
        self.assertEqual(captured[0]["comment_id"], comment["id"])

    def test_the_cap_on_retakes_is_read_on_the_entity_first(self):
        """
        A production caps its retakes, and a shot may raise or lower that
        cap for itself.
        """
        self.project.update({"max_retakes": 2})
        retake_status = self.generate_fixture_task_status_retake().serialize()
        task = self.task.serialize()

        comments_service._check_retake_capping(retake_status, task)
        self.task.update({"retake_count": 3})
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(
                retake_status, self.task.serialize()
            )

        self.shot.update({"data": {"max_retakes": 4}})
        entities_service.clear_entity_cache(task["entity_id"])
        comments_service._check_retake_capping(
            retake_status, self.task.serialize()
        )
        self.task.update({"retake_count": 5})
        with self.assertRaises(exception.WrongParameterException):
            comments_service._check_retake_capping(
                retake_status, self.task.serialize()
            )

    def test_a_production_capping_nothing_lets_every_retake_through(self):
        self.project.update({"max_retakes": 0})
        retake_status = self.generate_fixture_task_status_retake().serialize()
        self.task.update({"retake_count": 99})
        comments_service._check_retake_capping(
            retake_status, self.task.serialize()
        )

    def test_a_status_that_is_not_a_retake_is_never_capped(self):
        self.project.update({"max_retakes": 1})
        self.task.update({"retake_count": 99})
        comments_service._check_retake_capping(
            self.task_status.serialize(), self.task.serialize()
        )


class CreateCommentTestCase(CommentsTestCase):
    """
    The whole flow behind the comment route: the row, the status, the
    notifications, the news, and the comments the hashtags repost.
    """

    def test_a_comment_moves_its_task_and_feeds_the_stream(self):
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.wfa_status["id"]),
            text="please review",
        )

        self.assertEqual(comment["person"]["id"], self.person_id)
        self.assertEqual(comment["task_status"]["id"], self.wfa_status["id"])
        self.assertEqual(
            str(tasks_service.get_task_raw(self.task.id).task_status_id),
            self.wfa_status["id"],
        )
        self.assertEqual(
            News.query.filter_by(comment_id=comment["id"]).count(), 1
        )

    def test_a_comment_on_a_concept_stays_out_of_the_news_stream(self):
        concept = concepts_service.create_concept(self.project_id, "a concept")
        concept_task = self.generate_fixture_task(
            name="concept task", entity_id=concept["id"]
        )

        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(concept_task.id),
            task_status_id=str(self.task_status.id),
            text="on a concept",
        )

        self.assertEqual(
            News.query.filter_by(comment_id=comment["id"]).count(), 0
        )

    def test_a_hashtag_reposts_the_comment_on_the_sibling_tasks(self):
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

    def test_the_hashtags_can_be_left_alone(self):
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )

        comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="Please check #modeling",
            with_hashtags=False,
        )

        self.assertEqual(tasks_service.get_comments(modeling_task.id), [])

    def test_the_all_hashtag_reaches_every_other_task(self):
        modeling_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )
        concept_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_concept.id
        )

        comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="Important update for everyone #all",
        )

        for sibling in [modeling_task, concept_task]:
            self.assertEqual(len(tasks_service.get_comments(sibling.id)), 1)
        # The task the comment was posted on is not commented twice.
        self.assertEqual(len(tasks_service.get_comments(self.task.id)), 1)


class MentionTestCase(CommentsTestCase):
    """
    Reading names and task types out of the text of a comment.
    """

    def test_a_person_is_mentioned_by_full_name(self):
        self.assertEqual(
            comments_service.get_comment_mentions(
                self.project_id, "nothing to mention"
            ),
            [],
        )
        self.assertEqual(
            comments_service.get_comment_mentions(
                self.project_id, "mention @John Doe"
            ),
            [persons_service.get_person_raw(self.person_id)],
        )
        self.assertEqual(
            comments_service.get_comment_mention_ids(
                self.project_id, "mention @John Doe"
            ),
            [self.person_id],
        )

    def test_only_the_people_of_the_production_are_mentioned(self):
        """
        The mention is matched against the team: someone who cannot see the
        production must not be pulled into its comments.
        """
        outsider = self.generate_fixture_person(
            first_name="Alan", last_name="Smithee", email="alan@gmail.com"
        )
        self.assertEqual(
            comments_service.get_comment_mentions(
                self.project_id, f"mention @{outsider.full_name}"
            ),
            [],
        )

    def test_a_name_that_only_starts_a_word_is_not_a_mention(self):
        self.assertEqual(
            comments_service.get_comment_mentions(
                self.project_id, "mention @John Doelittle"
            ),
            [],
        )

    def test_a_department_is_mentioned_by_name(self):
        self.assertEqual(
            comments_service.get_comment_department_mentions(
                self.project_id, "nothing to mention"
            ),
            [],
        )
        self.assertEqual(
            comments_service.get_comment_department_mentions(
                self.project_id, "mention @Animation"
            ),
            [self.department_animation],
        )
        self.assertEqual(
            comments_service.get_comment_department_mention_ids(
                self.project_id, "mention @Animation"
            ),
            [str(self.department_animation.id)],
        )

    def test_the_mentions_of_a_comment_are_recomputed_from_its_text(self):
        comment = self.comment("mentions @Animation @John Doe")
        comment_to_edit = dict(comment, text="mentions nobody")
        Comment.get(comment["id"]).update({"text": "mentions nobody"})

        reset = comments_service.reset_mentions(comment_to_edit)

        self.assertEqual(reset["mentions"], [])
        self.assertEqual(reset["department_mentions"], [])

    def test_a_hashtag_names_a_task_type(self):
        for text, expected in [
            ("Great work! #animation", ["animation"]),
            ("Great work! #ANIMATION", ["animation"]),
            ("Great work! #animation.", ["animation"]),
            ("Great work! No hashtags here", []),
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    comments_service.get_comment_hashtags(text), expected
                )
        self.assertEqual(
            sorted(
                comments_service.get_comment_hashtags(
                    "Check this out #animation #lighting"
                )
            ),
            ["animation", "lighting"],
        )

    def test_the_all_hashtag_swallows_the_others(self):
        for text in [
            "Great work! #all #animation #lighting",
            "Great work! #all",
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    comments_service.get_comment_hashtags(text), ["all"]
                )

    def test_the_hashtags_pick_the_tasks_to_repost_on(self):
        tasks = [
            {"id": "1", "task_type_name": "animation"},
            {"id": "2", "task_type_name": "modeling"},
            {"id": "3", "task_type_name": "lighting"},
            {"id": "4", "task_type_name": "rigging"},
        ]
        animation = {"id": "tt1", "name": "Animation"}

        def names(hashtags):
            return sorted(
                task["task_type_name"]
                for task in comments_service.filter_tasks_by_hashtags(
                    tasks, hashtags, animation
                )
            )

        self.assertEqual(names(["modeling"]), ["modeling"])
        self.assertEqual(
            names(["modeling", "lighting"]), ["lighting", "modeling"]
        )
        # The task type the comment was posted on never gets a copy.
        self.assertEqual(names(["animation", "modeling"]), ["modeling"])
        self.assertEqual(names(["all"]), ["lighting", "modeling", "rigging"])
        self.assertEqual(names([]), [])


class AttachmentTestCase(CommentsTestCase):
    """
    The files hanging off a comment.
    """

    def attach(self, comment, filename):
        return comments_service.create_attachment(
            comment, self.uploaded_file(filename)
        )

    def test_an_attachment_carries_its_name_and_its_weight(self):
        attachment = self.attach(self.comment(), "notes.txt")
        self.assertEqual(attachment["name"], "notes.txt")
        self.assertEqual(attachment["extension"], "txt")
        self.assertGreater(attachment["size"], 0)

    def test_an_attachment_is_read_back_from_the_store(self):
        attachment = self.attach(self.comment(), "notes.txt")
        path = comments_service.get_attachment_file_path(attachment)
        with open(path, "rb") as attachment_file:
            self.assertEqual(attachment_file.read(), b"attachment content")

    def test_a_storage_failure_leaves_nothing_behind(self):
        comment = self.comment()
        os.makedirs(config.TMP_DIR, exist_ok=True)
        tmp_files_before = set(os.listdir(config.TMP_DIR))

        with patch(
            "zou.app.services.comments_service.file_store.add_file",
            side_effect=OSError("storage down"),
        ):
            with self.assertRaises(OSError):
                self.attach(comment, "notes.txt")

        self.assertEqual(AttachmentFile.query.count(), 0)
        self.assertEqual(set(os.listdir(config.TMP_DIR)), tmp_files_before)

    def test_a_randomized_name_keeps_its_extension(self):
        attachment = comments_service.create_attachment(
            self.comment(), self.uploaded_file("notes.txt"), randomize=True
        )
        self.assertTrue(attachment["name"].startswith("notes-"))
        self.assertTrue(attachment["name"].endswith(".txt"))
        self.assertEqual(attachment["extension"], "txt")

    def test_an_attachment_named_after_an_unknown_reply_stays_on_the_comment(
        self,
    ):
        attachment = comments_service.create_attachment(
            self.comment(),
            self.uploaded_file("notes.txt"),
            reply_id=str(fields.gen_uuid()),
        )
        self.assertIsNone(attachment.get("reply_id"))

    def test_a_new_attachment_shows_on_the_comment(self):
        """
        The route reads the comment through the memoized serialization,
        which is what every later read gets too: an attachment added to a
        comment that was already read would not show up until the window
        closes.
        """
        comment = self.comment()
        tasks_service.get_comment(comment["id"], relations=True)

        _, attached = comments_service.add_attachments_to_comment(
            comment, {"file": self.uploaded_file("notes.txt")}
        )

        self.assertEqual(
            tasks_service.get_comment(comment["id"], relations=True)[
                "attachment_files"
            ],
            [attached[0]["id"]],
        )

    def assert_the_attachment_listing_is_scoped(self, list_files, scope_id):
        """
        The listing carries the attachments of the thing it is asked about,
        and answers empty for an id that owns none.
        """
        attachment = self.attach(self.comment(), "notes.txt")

        attachments = list_files(scope_id)

        self.assertEqual(
            [attached["id"] for attached in attachments], [attachment["id"]]
        )
        self.assertEqual(list_files(fields.gen_uuid()), [])

    def test_the_attachments_of_a_production_are_listed(self):
        self.assert_the_attachment_listing_is_scoped(
            comments_service.get_all_attachment_files_for_project,
            self.project_id,
        )

    def test_the_attachments_of_a_task_are_listed(self):
        self.assert_the_attachment_listing_is_scoped(
            comments_service.get_all_attachment_files_for_task,
            str(self.task.id),
        )

    def test_only_raster_images_are_served_inline(self):
        """
        An SVG can carry a script and would run in the origin of Kitsu, so
        it is downloaded rather than displayed.
        """
        for mimetype in [
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "IMAGE/PNG",
            "image/jpeg; charset=binary",
        ]:
            with self.subTest(mimetype=mimetype):
                self.assertTrue(
                    comments_service.is_inline_safe_mimetype(mimetype)
                )
        for mimetype in [
            "image/svg+xml",
            "text/html",
            "application/pdf",
            "application/octet-stream",
            "",
            None,
        ]:
            with self.subTest(mimetype=mimetype):
                self.assertFalse(
                    comments_service.is_inline_safe_mimetype(mimetype)
                )


class ReplyTestCase(CommentsTestCase):
    """
    The thread hanging under a comment. Replies live in a JSONB column of
    the comment they belong to.
    """

    def test_a_reply_lands_under_its_comment(self):
        comment = self.comment("comment that starts a thread")
        reply = comments_service.reply_comment(
            comment["id"], "first reply", person_id=self.user["id"]
        )

        comment = tasks_service.get_comment(comment["id"])

        self.assertEqual(len(comment["replies"]), 1)
        self.assertEqual(comment["replies"][0]["text"], "first reply")
        self.assertEqual(comment["replies"][0]["person_id"], self.user["id"])
        self.assertEqual(reply["person"]["id"], self.user["id"])

    def test_the_mentions_of_a_reply_are_read_off_its_text(self):
        comment = self.comment("comment that starts a thread")
        comments_service.reply_comment(
            comment["id"],
            "mention @Animation and @John Doe",
            person_id=self.user["id"],
        )

        reply = tasks_service.get_comment(comment["id"])["replies"][0]

        self.assertEqual(reply["mentions"], [self.person_id])
        self.assertEqual(
            reply["department_mentions"],
            [str(self.department_animation.id)],
        )

    def test_a_reply_is_announced(self):
        comment = self.comment()
        captured = self.capture_events("comment:reply")
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["task_id"], str(self.task.id))
        self.assertEqual(captured[0]["comment_id"], comment["id"])
        self.assertEqual(captured[0]["reply_id"], reply["id"])

    def test_a_reply_is_read_by_id(self):
        comment = self.comment()
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        self.assertEqual(
            comments_service.get_reply(comment["id"], reply["id"])["text"],
            "the reply",
        )
        self.assertRaises(
            exception.ReplyNotFoundException,
            comments_service.get_reply,
            comment["id"],
            fields.gen_uuid(),
        )

    def test_a_deleted_reply_is_gone_from_its_comment(self):
        comment = self.comment()
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
        self.assertEqual(
            tasks_service.get_comment(comment["id"])["replies"], []
        )

    def test_a_deleted_reply_takes_its_attachments_with_it(self):
        """
        A reply carries its own attachments, and they go with it. The
        comment's own attachments stay.
        """
        comment = self.comment()
        reply = comments_service.reply_comment(
            comment["id"], "the reply", person_id=self.user["id"]
        )
        comments_service.add_attachments_to_comment(
            comment, {"file": self.uploaded_file("kept.txt")}
        )
        comments_service.add_attachments_to_comment(
            tasks_service.get_comment(comment["id"], relations=True),
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

    def test_a_deleted_reply_takes_its_notifications_with_it(self):
        comment = self.comment()
        reply = comments_service.reply_comment(
            comment["id"],
            "mention @John Doe",
            person_id=self.user["id"],
        )
        self.assertGreater(
            Notification.query.filter_by(reply_id=reply["id"]).count(), 0
        )

        comments_service.delete_reply(comment["id"], reply["id"])

        self.assertEqual(
            Notification.query.filter_by(reply_id=reply["id"]).count(), 0
        )


class AcknowledgeTestCase(CommentsTestCase):
    """
    The checkmark a supervisor puts on a comment. The same call adds it and
    takes it back.
    """

    def acknowledge(self, comment):
        return self.post(
            f"data/tasks/{self.task.id}/comments/{comment['id']}/ack", {}, 200
        )

    def test_the_same_call_acknowledges_and_takes_it_back(self):
        comment = self.comment("to ack")
        self.assertIn(
            self.user["id"], self.acknowledge(comment)["acknowledgements"]
        )
        self.assertEqual(self.acknowledge(comment)["acknowledgements"], [])

    def test_an_acknowledgement_shows_on_the_comment(self):
        """
        Kitsu draws the checkmark from the comment it reads back, not from
        the answer of the acknowledgement call.
        """
        comment = self.comment("to ack")
        tasks_service.get_comment(comment["id"], relations=True)

        self.acknowledge(comment)

        self.assertEqual(
            tasks_service.get_comment(comment["id"], relations=True)[
                "acknowledgements"
            ],
            [self.user["id"]],
        )

    def test_an_acknowledgement_is_announced(self):
        comment = self.comment("to ack")
        captured = self.capture_events("comment:acknowledge")
        self.acknowledge(comment)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["person_id"], self.user["id"])


class MoveCommentTestCase(CommentsTestCase):
    """
    Moving a comment posted on the wrong task type of the same entity.
    """

    def setUp(self):
        super().setUp()
        self.target_task = self.generate_fixture_shot_task(
            name="main", task_type_id=self.task_type_modeling.id
        )

    def test_a_moved_comment_belongs_to_its_new_task(self):
        comment = self.comment("wrong task type")

        moved = comments_service.move_comment_to_task(
            comment["id"], str(self.target_task.id)
        )

        self.assertEqual(moved["object_id"], str(self.target_task.id))
        self.assertEqual(
            [
                found["id"]
                for found in tasks_service.get_comments(self.target_task.id)
            ],
            [comment["id"]],
        )
        self.assertEqual(tasks_service.get_comments(self.task.id), [])

    def test_a_moved_comment_keeps_what_it_carries(self):
        comment = self.comment(
            "mention @John Doe",
            created_at="2024-01-23 10:00:00",
            files={"file": self.uploaded_file("notes.txt")},
        )

        moved = comments_service.move_comment_to_task(
            comment["id"], str(self.target_task.id)
        )

        self.assertEqual(moved["created_at"], "2024-01-23T10:00:00")
        self.assertEqual(moved["text"], "mention @John Doe")
        self.assertEqual(moved["mentions"], [self.person_id])
        self.assertEqual(
            [
                attachment.name
                for attachment in AttachmentFile.get_all_by(
                    comment_id=comment["id"]
                )
            ],
            ["notes.txt"],
        )

    def test_the_news_of_a_moved_comment_follows_it(self):
        comment = comments_service.create_comment(
            person_id=self.person_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="wrong task type",
        )

        comments_service.move_comment_to_task(
            comment["id"], str(self.target_task.id)
        )

        self.assertEqual(
            [
                str(news.task_id)
                for news in News.query.filter_by(comment_id=comment["id"])
            ],
            [str(self.target_task.id)],
        )

    def test_a_moved_comment_is_announced_on_both_tasks(self):
        comment = self.comment("wrong task type")
        removed = self.capture_events("comment:delete")
        added = self.capture_events("comment:new")

        comments_service.move_comment_to_task(
            comment["id"], str(self.target_task.id)
        )

        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["task_id"], str(self.target_task.id))

    def test_a_comment_only_moves_inside_its_own_entity(self):
        other_task = self.generate_fixture_task(name="on the asset")
        comment = self.comment("wrong task type")

        for label, target_id in [
            ("same task", str(self.task.id)),
            ("another entity", str(other_task.id)),
        ]:
            with self.subTest(label=label):
                self.assertRaises(
                    exception.WrongParameterException,
                    comments_service.move_comment_to_task,
                    comment["id"],
                    target_id,
                )

    def test_a_comment_carrying_a_preview_does_not_move(self):
        """
        A preview revision belongs to the task it was published on: the
        comment showing it cannot leave without it.
        """
        comment = self.comment("with a preview")
        tasks_service.add_preview_file_to_comment(
            comment["id"], self.user["id"], str(self.task.id)
        )

        self.assertRaises(
            exception.WrongParameterException,
            comments_service.move_comment_to_task,
            comment["id"],
            str(self.target_task.id),
        )
