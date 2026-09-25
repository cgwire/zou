from tests.base import ApiDBTestCase

from zou.app.models.project import Project


class QueryTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()

        self.project_id = self.project.id
        project = Project.create(
            name="Kitchen", project_status_id=self.open_status.id
        )
        self.project2_id = project.id

        self.generate_fixture_asset("Asset 1")
        self.generate_fixture_asset("Asset 2")
        self.generate_fixture_asset("Asset 3")
        self.generate_fixture_asset_character("Asset char 1")
        self.generate_fixture_asset_character("Asset char 2")

    def test_malformed_filters_return_400(self):
        self.get('data/projects?id=["broken', 400)
        self.get("data/projects?is_clients_isolated=notabool", 400)

    def test_values_the_driver_refuses_return_400(self):
        """
        Only UUIDs and booleans are validated before the query runs. The
        driver rejects the rest on execution, which used to surface as a 500.
        """
        self.get("data/projects?created_at=yesterday", 400)
        self.get("data/tasks?priority=abc", 400)
        self.get("data/tasks?episode_id=abc", 400)

    def test_pagination_needs_a_positive_limit(self):
        self.get("data/projects?page=1&limit=-1", 400)
        self.get("data/projects?page=1&limit=0")

    def test_get_by_name(self):
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 5)
        entities = self.get(f"data/entities?name={entities[0]['name']}")
        self.assertEqual(len(entities), 1)
        entities = self.get(
            f"data/entities?name={entities[0]['name']}&project_id={self.project_id}"
        )
        self.assertEqual(len(entities), 1)
        entities = self.get(
            f"data/entities?name={entities[0]['name']}&project_id={self.project2_id}"
        )
        self.assertEqual(entities, [])
