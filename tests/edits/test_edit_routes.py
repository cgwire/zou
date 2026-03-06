from tests.edits.base import BaseEditTestCase


class EditRoutesTestCase(BaseEditTestCase):
    def test_get_all_edits(self):
        edits = self.get("/data/edits")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["name"], "Edit")

    def test_get_edit_preview_files(self):
        result = self.get(f"/data/edits/{self.edit_id}/preview-files")
        self.assertIsInstance(result, dict)

    def test_get_edit_preview_files_with_data(self):
        self.generate_fixture_preview_file(
            task_id=self.task.id,
        )
        result = self.get(f"/data/edits/{self.edit_id}/preview-files")
        self.assertTrue(len(result) > 0)

    def test_get_edit_versions(self):
        result = self.get(f"/data/edits/{self.edit_id}/versions")
        self.assertIsInstance(result, list)
