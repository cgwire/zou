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

    def test_get_edits_with_tasks(self):
        result = self.get("/data/edits/with-tasks")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Edit")

    def test_get_edits_with_tasks_include_task_data(self):
        self.task.update({"data": {"render_layer": "bg"}})
        result = self.get("/data/edits/with-tasks")
        task = next(
            task
            for task in result[0]["tasks"]
            if task["id"] == str(self.task.id)
        )
        self.assertEqual(task["data"], {"render_layer": "bg"})

    def test_get_edits_with_tasks_wrong_id_format(self):
        self.get("/data/edits/with-tasks?project_id=not-a-uuid", 400)
        self.get("/data/edits/with-tasks?episode_id=not-a-uuid", 400)
        self.get("/data/edits/with-tasks?id=not-a-uuid", 400)
