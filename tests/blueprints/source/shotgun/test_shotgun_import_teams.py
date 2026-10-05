from tests.blueprints.source.shotgun.base import ShotgunTestCase
from zou.app.services import projects_service


class ImportShotgunProjectConnectionsTestCase(ShotgunTestCase):
    def setUp(self):
        super().setUp()

    def test_import_project_connections(self):
        self.load_fixture("persons")
        self.load_fixture("projects")
        self.load_fixture("projectconnections")
        projects = self.get("data/projects")
        projects = sorted(projects, key=lambda x: x["name"])
        project = projects_service.get_project(
            projects[0]["id"],
            relations=True,
        )
        self.assertEqual(project["name"], "Agent327")
        self.assertEqual(len(project["team"]), 2)
        project = projects_service.get_project(
            projects[1]["id"],
            relations=True,
        )
        self.assertEqual(len(project["team"]), 1)

    def test_import_projects_twice(self):
        self.load_fixture("persons")
        self.load_fixture("projects")
        self.load_fixture("projectconnections")
        self.load_fixture("projectconnections")
        projects = self.get("data/projects")
        projects = sorted(projects, key=lambda x: x["name"])
        project = projects_service.get_project(
            projects[0]["id"],
            relations=True,
        )
        self.assertEqual(project["name"], "Agent327")
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

        api_path = "/import/shotgun/project-connections"
        self.projects = self.post(api_path, [sg_project_persons], 200)
        self.assertEqual(len(self.projects), 1)

        projects = self.get("data/projects")
        projects = sorted(projects, key=lambda x: x["name"])
        project = projects_service.get_project(
            projects[0]["id"],
            relations=True,
        )
        self.assertEqual(project["name"], "Agent327")
        self.assertEqual(len(project["team"]), 1)

    def test_remove_project_connection(self):
        """
        The removal route looked the link up through BaseMixin.get_by,
        which the bare link table does not have: it answered 500 whatever
        the body.
        """
        self.load_fixture("persons")
        self.load_fixture("projects")
        self.load_fixture("projectconnections")
        projects = sorted(self.get("data/projects"), key=lambda x: x["name"])
        agent = projects_service.get_project(projects[0]["id"], relations=True)
        self.assertEqual(len(agent["team"]), 2)

        result = self.post(
            "/import/shotgun/remove/project-connection", {"id": 3}, 200
        )
        self.assertTrue(result["success"])
        projects_service.clear_project_cache(agent["id"])
        agent = projects_service.get_project(agent["id"], relations=True)
        self.assertEqual(len(agent["team"]), 1)

        # An unknown connection is not an error.
        result = self.post(
            "/import/shotgun/remove/project-connection", {"id": 999}, 200
        )
        self.assertTrue(result["success"])

    def test_remove_project_connection_needs_an_admin(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.post("/import/shotgun/remove/project-connection", {"id": 3}, 403)
