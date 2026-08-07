from tests.blueprints.edits.base import BaseEditTestCase


class EditRoutesTestCase(BaseEditTestCase):
    def test_get_all_edits(self):
        edits = self.get("/data/edits")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["name"], "Edit")

    def test_get_edit_preview_files(self):
        """
        Keyed by task type, and a task type shows up only once it has a
        preview.
        """
        path = f"/data/edits/{self.edit_id}/preview-files"
        self.assertEqual(self.get(path), {})
        preview_file = self.generate_fixture_preview_file(task_id=self.task.id)

        result = self.get(path)

        self.assertEqual(
            [preview["id"] for preview in result[str(self.task.task_type_id)]],
            [str(preview_file.id)],
        )

    def test_get_edit_versions(self):
        # Nothing has been published on this edit yet.
        self.assertEqual(self.get(f"/data/edits/{self.edit_id}/versions"), [])

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

    def test_get_edits_for_episode(self):
        edits = self.get(f"/data/episodes/{self.episode_id}/edits")

        self.assertEqual([edit["id"] for edit in edits], [str(self.edit_id)])

    def test_get_edit_tasks_for_episode(self):
        """
        The tasks of the edits an episode holds. A shot of that episode hangs
        one level deeper, under a sequence, and none of its tasks belong here.
        """
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()

        tasks = self.get(f"/data/episodes/{self.episode_id}/edit-tasks")

        self.assertEqual(
            sorted(task["entity_id"] for task in tasks),
            sorted([str(self.edit_id)] * 2),
        )

    def test_get_edits_with_tasks_wrong_id_format(self):
        self.get("/data/edits/with-tasks?project_id=not-a-uuid", 400)
        self.get("/data/edits/with-tasks?episode_id=not-a-uuid", 400)
        self.get("/data/edits/with-tasks?id=not-a-uuid", 400)
