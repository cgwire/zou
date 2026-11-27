from tests.base import ApiDBTestCase


class TasksCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_task_type()

    def test_export(self):
        csv_task_types = self.get_raw("export/csv/task-types.csv")
        expected_result = """Department;Name\r
Animation;Animation\r
Animation;Layout\r
Modeling;Concept\r
Modeling;Modeling\r
Modeling;Shaders\r
"""
        self.assertEqual(csv_task_types, expected_result)

    def test_export_file_name(self):
        response = self.app.get(
            "export/csv/task-types.csv", headers=self.base_headers
        )
        response.get_data()
        self.assertEqual(
            response.headers["Content-Disposition"],
            "attachment; filename=kitsu_task_types_export.csv",
        )
