from tests.base import ApiDBTestCase
from zou.app.services import projects_service


class TasksCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_task()
        self.maxDiff = None

    headers = "Project;Task Type;Episode;Sequence;Entity Type;Entity;Assigner;Assignees;Duration;Estimation;Start date;Due date;WIP date;Validation date;Task Status\r\n"
    row = "Cosmos Landromat;Shaders;;;Props;Tree;Ema Peel;John Doe;50.0;40.0;2017-02-20;2017-02-28;2017-02-22;;Open\r\n"

    def test_export(self):
        csv_tasks = self.get_raw("/export/csv/tasks.csv")
        self.assertEqual(csv_tasks, self.headers + self.row)

    def test_export_for_a_manager_is_limited_to_their_projects(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        csv_tasks = self.get_raw("/export/csv/tasks.csv")
        self.assertEqual(csv_tasks, self.headers)

        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        csv_tasks = self.get_raw("/export/csv/tasks.csv")
        self.assertEqual(csv_tasks, self.headers + self.row)
