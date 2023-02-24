from tests.base import ApiDBTestCase


class TasksCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super(TasksCsvExportTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.maxDiff = None

    def test_export(self):
        csv_tasks = self.get_raw("/export/csv/tasks.csv")
        expected_result = """Project;Task Type;Episode;Sequence;Entity Type;Entity;Assigner;Assignees;Duration;Estimation;Start date;Due date;WIP date;Validation date;Task Status\r
Cosmos Landromat;Shaders;;;Props;Tree;Ema Peel;John Doe;50.0;40.0;2017-02-20;2017-02-28;2017-02-22;;Open\r
"""
        self.assertEqual(csv_tasks, expected_result)
