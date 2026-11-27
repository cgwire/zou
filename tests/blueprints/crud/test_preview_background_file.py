from tests.base import ApiDBTestCase
from zou.app.utils import fields


class PreviewBackgroundFileTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_preview_background_file("test")
        self.generate_fixture_preview_background_file("test1")
        self.project = self.generate_fixture_project()

    def test_get_preview_background_files(self):
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 2)

    def test_get_preview_background_file(self):
        preview_background_file = self.get_first(
            "data/preview-background-files"
        )
        preview_background_file_again = self.get(
            f"data/preview-background-files/{preview_background_file['id']}"
        )
        self.assertEqual(
            preview_background_file, preview_background_file_again
        )
        self.get_404(f"data/preview-background-files/{fields.gen_uuid()}")

    def test_create_preview_background_file(self):
        data = {
            "name": "test4",
        }
        self.preview_background_file = self.post(
            "data/preview-background-files", data
        )
        self.assertIsNotNone(self.preview_background_file["id"])

        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 3)

    def test_update_preview_background_file(self):
        preview_background_file = self.get_first(
            "data/preview-background-files"
        )
        data = {"name": "test4"}
        self.put(
            f"data/preview-background-files/{preview_background_file['id']}",
            data,
        )
        preview_background_file_again = self.get(
            f"data/preview-background-files/{preview_background_file['id']}"
        )
        self.assertEqual(
            data["name"],
            preview_background_file_again["name"],
        )
        self.put_404(
            f"data/preview-background-files/{fields.gen_uuid()}", data
        )

    def test_delete_preview_background_file(self):
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 2)
        preview_background_file = preview_background_files[0]
        self.delete(
            f"data/preview-background-files/{preview_background_file['id']}"
        )
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 1)
        self.delete_404(f"data/preview-background-files/{fields.gen_uuid()}")

    def test_the_default_background_is_one_of_the_project(self):
        path = f"data/projects/{self.project.id}"
        background_id = str(self.preview_background_file.id)
        self.put(
            path, {"default_preview_background_file_id": background_id}, 400
        )
        self.put(
            path,
            {
                "preview_background_files": [background_id],
                "default_preview_background_file_id": background_id,
            },
        )
        self.assertEqual(
            self.get(path)["default_preview_background_file_id"],
            background_id,
        )
