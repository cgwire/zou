from tests.base import ApiDBTestCase
from zou.app.services import (
    projects_service,
    time_spents_service,
)


class TasksCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.project = self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        person_id = str(self.generate_fixture_person().id)
        task_id = str(self.generate_fixture_task().id)
        time_spents_service.create_or_update_time_spent(
            task_id, person_id, "2023-03-04", 500
        )
        self.generate_fixture_project_closed()

        self.project = self.project_closed
        self.generate_fixture_asset()
        task_id = str(self.generate_fixture_task().id)
        time_spents_service.create_or_update_time_spent(
            task_id, person_id, "2022-03-04", 200
        )
        self.maxDiff = None

    def test_export(self):
        csv_tasks = self.get_raw("/export/csv/time-spents.csv")
        expected_result = """Project;Person;Entity Type Name;Entity;Task Type;Date;Time spent\r
Cosmos Landromat;John Doe;Props;Tree;Shaders;2023-03-04;500.0\r
"""
        self.assertEqual(csv_tasks, expected_result)

    def test_export_for_a_manager_is_limited_to_their_projects(self):
        headers = "Project;Person;Entity Type Name;Entity;Task Type;Date;Time spent\r\n"
        row = (
            "Cosmos Landromat;John Doe;Props;Tree;Shaders;2023-03-04;500.0\r\n"
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        csv_time_spents = self.get_raw("/export/csv/time-spents.csv")
        self.assertEqual(csv_time_spents, headers)

        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        csv_time_spents = self.get_raw("/export/csv/time-spents.csv")
        self.assertEqual(csv_time_spents, headers + row)
