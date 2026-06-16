import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.models.task import Task


class ImportCsvTaskTypeEstimationsTestCase(ApiDBTestCase):
    def setUp(self):
        super(ImportCsvTaskTypeEstimationsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()

    def write_csv(self, content):
        """
        Write CSV content to a temporary file and return its path.
        """
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as f:
            f.write(content)
        return file_path

    def test_import_matches_asset_entity(self):
        # For assets, a row is matched on its asset type ("Props") as Parent
        # and its asset name ("Tree") as Entity.
        self.generate_fixture_task()
        path = (
            f"/import/csv/projects/{self.project.id}"
            f"/task-types/{self.task_type.id}/estimations"
        )
        content = "Parent,Entity,Start date\nProps,Tree,2024-01-05\n"
        self.upload_file(path, self.write_csv(content))

        task = Task.get(self.task.id)
        self.assertEqual(task.start_date.strftime("%Y-%m-%d"), "2024-01-05")
