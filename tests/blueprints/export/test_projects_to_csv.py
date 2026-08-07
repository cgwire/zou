from tests.base import ApiDBTestCase


class OutputFileTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()

    def test_export(self):
        csv_projects = self.get_raw("/export/csv/projects.csv")
        expected_result = """Name;Status\r
Cosmos Landromat;Open\r\n"""
        self.assertEqual(csv_projects, expected_result)
