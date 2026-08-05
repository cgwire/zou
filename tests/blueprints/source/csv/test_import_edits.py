import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.services import edits_service, shots_service


class ImportCsvEditsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.path = f"/import/csv/projects/{self.project.id}/edits"

    def write_csv(self, content):
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def test_import_edits(self):
        self.upload_file(
            self.path,
            self.write_csv("Name,Description\nOpening,The first edit\n"),
        )

        edits = edits_service.get_edits_for_project(str(self.project.id))
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["name"], "Opening")
        self.assertEqual(edits[0]["description"], "The first edit")

    def test_import_creates_the_missing_episode_of_a_tv_show(self):
        """
        On a tv show the Episode column names where the edit belongs, and an
        episode that does not exist yet is created along the way, so a studio
        can seed a season from one file.
        """
        self.project.update({"production_type": "tvshow"})
        self.upload_file(
            self.path,
            self.write_csv("Name,Episode\nOpening,E01\nEnding,E01\n"),
        )

        episodes = shots_service.get_episodes({"project_id": self.project.id})
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["name"], "E01")

        edits = edits_service.get_edits_for_episode(episodes[0]["id"])
        self.assertEqual(
            sorted(edit["name"] for edit in edits), ["Ending", "Opening"]
        )

    def test_episode_column_is_refused_outside_a_tv_show(self):
        """
        A short has no episode to hang an edit from, so the column is a
        mistake worth reporting rather than a value to ignore.
        """
        self.upload_file(
            self.path,
            self.write_csv("Name,Episode\nOpening,E01\n"),
            code=400,
        )
        self.assertEqual(
            edits_service.get_edits_for_project(str(self.project.id)), []
        )
