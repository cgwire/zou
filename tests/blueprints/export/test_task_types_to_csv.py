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
