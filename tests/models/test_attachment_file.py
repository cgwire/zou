from tests.base import ApiDBTestCase
from zou.app.models.attachment_file import AttachmentFile
from zou.app.utils import fields


class AttachmentFileTestCase(ApiDBTestCase):
    def setUp(self):
        super(AttachmentFileTestCase, self).setUp()
        self.generate_data(AttachmentFile, 3)

    def test_get_attachment_files(self):
        attachment_files = self.get("data/attachment-files")
        self.assertEqual(len(attachment_files), 3)

    def test_get_attachment_file(self):
        attachment_file = self.get_first("data/attachment-files")
        attachment_file_again = self.get(
            "data/attachment-files/%s" % attachment_file["id"]
        )
        self.assertEqual(attachment_file, attachment_file_again)
        self.get_404("data/attachment-files/%s" % fields.gen_uuid())

    def test_create_attachment_file(self):
        data = {
            "name": "test_file",
            "extension": "png",
            "size": 1024,
            "mimetype": "image/png",
        }
        attachment_file = self.post("data/attachment-files", data)
        self.assertIsNotNone(attachment_file["id"])
        attachment_files = self.get("data/attachment-files")
        self.assertEqual(len(attachment_files), 4)

    def test_update_attachment_file(self):
        attachment_file = self.get_first("data/attachment-files")
        data = {"name": "updated_file"}
        self.put(
            "data/attachment-files/%s" % attachment_file["id"], data
        )
        attachment_file_again = self.get(
            "data/attachment-files/%s" % attachment_file["id"]
        )
        self.assertEqual(data["name"], attachment_file_again["name"])
        self.put_404(
            "data/attachment-files/%s" % fields.gen_uuid(), data
        )

    def test_delete_attachment_file(self):
        attachment_files = self.get("data/attachment-files")
        self.assertEqual(len(attachment_files), 3)
        attachment_file = attachment_files[0]
        self.delete(
            "data/attachment-files/%s" % attachment_file["id"]
        )
        attachment_files = self.get("data/attachment-files")
        self.assertEqual(len(attachment_files), 2)
        self.delete_404(
            "data/attachment-files/%s" % fields.gen_uuid()
        )
