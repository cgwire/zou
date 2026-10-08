import os
from unittest.mock import patch

from zou.app import config
from zou.app.models.attachment_file import AttachmentFile
from zou.app.services import attachment_files_service
from zou.app.utils import fields
from tests.services.cases import CommentsTestCase


class AttachmentTestCase(CommentsTestCase):
    def attach(self, comment, filename):
        return attachment_files_service.create_attachment(
            comment, self.uploaded_file(filename)
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

    def test_an_attachment_carries_its_name_and_its_weight(self):
        attachment = self.attach(self.comment(), "notes.txt")
        self.assertEqual(attachment["name"], "notes.txt")
        self.assertEqual(attachment["extension"], "txt")
        self.assertGreater(attachment["size"], 0)

    def test_an_attachment_is_read_back_from_the_store(self):
        attachment = self.attach(self.comment(), "notes.txt")
        path = attachment_files_service.get_attachment_file_path(attachment)
        with open(path, "rb") as attachment_file:
            self.assertEqual(attachment_file.read(), b"attachment content")

    def test_a_storage_failure_leaves_nothing_behind(self):
        comment = self.comment()
        os.makedirs(config.TMP_DIR, exist_ok=True)
        tmp_files_before = set(os.listdir(config.TMP_DIR))

        with patch(
            "zou.app.services.attachment_files_service.file_store.add_file",
            side_effect=OSError("storage down"),
        ):
            with self.assertRaises(OSError):
                self.attach(comment, "notes.txt")

        self.assertEqual(AttachmentFile.query.count(), 0)
        self.assertEqual(set(os.listdir(config.TMP_DIR)), tmp_files_before)

    def test_a_randomized_name_keeps_its_extension(self):
        attachment = attachment_files_service.create_attachment(
            self.comment(), self.uploaded_file("notes.txt"), randomize=True
        )
        self.assertTrue(attachment["name"].startswith("notes-"))
        self.assertTrue(attachment["name"].endswith(".txt"))
        self.assertEqual(attachment["extension"], "txt")

    def test_an_attachment_named_after_an_unknown_reply_stays_on_the_comment(
        self,
    ):
        attachment = attachment_files_service.create_attachment(
            self.comment(),
            self.uploaded_file("notes.txt"),
            reply_id=str(fields.gen_uuid()),
        )
        self.assertIsNone(attachment.get("reply_id"))

    def test_the_attachments_of_a_production_are_listed(self):
        self.assert_the_attachment_listing_is_scoped(
            attachment_files_service.get_all_attachment_files_for_project,
            self.project_id,
        )

    def test_the_attachments_of_a_task_are_listed(self):
        self.assert_the_attachment_listing_is_scoped(
            attachment_files_service.get_all_attachment_files_for_task,
            str(self.task.id),
        )
