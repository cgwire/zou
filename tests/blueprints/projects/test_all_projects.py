from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class OpenProjectRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_project_closed()

    def test_all_projects(self):
        projects = self.get("data/projects/all/")

        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["name"], self.project.name)
        self.assertEqual(projects[0]["project_status_name"], "Open")
        self.assertEqual(projects[1]["project_status_name"], "closed")

    def test_get_project_by_name(self):
        project = self.get_first(
            f"data/projects/all?name={self.project.name.lower()}"
        )
        self.assertEqual(project["id"], str(self.project.id))

    def test_get_project_by_name_as_a_team_member(self):
        # The non admin branch called user_service.get_project_by_name,
        # which did not exist.
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        project = self.get_first(
            f"data/projects/all?name={self.project.name.lower()}"
        )
        self.assertEqual(project["id"], str(self.project.id))
        self.get("data/projects/all?name=nowhere", 404)
