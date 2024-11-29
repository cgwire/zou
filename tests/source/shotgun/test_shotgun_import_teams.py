from tests.source.shotgun.base import ShotgunTestCase
from zou.app.services import projects_service


class ImportShotgunProjectConnectionsTestCase(ShotgunTestCase):
    def setUp(self):
        super(ImportShotgunProjectConnectionsTestCase, self).setUp()

    def test_import_project_connections(self):
        self.load_fixture("persons")
        self.load_fixture("projects")
        self.load_fixture("projectconnections")
        projects = self.get("data/projects")
        project = projects_service.get_project(
            projects[0]["id"],
            relations=True,
        )
        self.assertEqual(len(project["team"]), 1)
        project = projects_service.get_project(
            projects[1]["id"],
            relations=True,
        )
        self.assertEqual(len(project["team"]), 2)

    def test_import_projects_twice(self):
        self.load_fixture("persons")
        self.load_fixture("projects")
        self.load_fixture("projectconnections")
        self.load_fixture("projectconnections")
        projects = self.get("data/projects")
        project = projects_service.get_project(
            projects[0]["id"],
            relations=True,
        )
        self.assertEqual(len(project["team"]), 2)

    def test_import_project_connection(self):
        self.load_fixture("persons")
        self.load_fixture("projects")
        sg_project_persons = {
            "id": 1,
            "project": {"type": "Project", "id": 1, "name": "Agent327"},
            "user": {"type": "HumanUser", "id": 1, "name": "Jhon Doe"},
            "type": "ProjectUserConnection",
        }

        api_path = "/import/shotgun/projectconnections"
        self.projects = self.post(api_path, [sg_project_persons], 200)
        self.assertEqual(len(self.projects), 1)

        projects = self.get("data/projects")
        project = projects_service.get_project(
            projects[1]["id"],
            relations=True,
        )
        self.assertEqual(len(project["team"]), 1)
