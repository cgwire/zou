from sqlalchemy import event

from tests.base import ApiDBTestCase
from zou.app import db
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


class SameProjectDictTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_task_type()
        projects_service.create_project_task_type_link(
            self.project.id, self.task_type.id, 3
        )

    def test_every_project_route_serves_the_same_dict(self):
        project_id = str(self.project.id)
        reads = {
            "list": self.get("data/projects")[0],
            "all": self.get("data/projects/all")[0],
            "open": self.get("data/projects/open")[0],
            "single": self.get(f"data/projects/{project_id}"),
            "context": self.get("data/user/context")["projects"][0],
        }
        keys = set(reads["single"].keys())
        for route, project in reads.items():
            self.assertEqual(set(project.keys()), keys, route)
            self.assertEqual(
                project["task_types_priority"],
                {str(self.task_type.id): 3},
                route,
            )
            self.assertEqual(project["project_status_name"], "Open", route)

    def test_project_lists_cost_no_query_per_project(self):
        def count_queries(path):
            # The admin open listing is memoized: it is read afresh.
            projects_service.clear_project_cache("")
            statements = []

            def record(conn, cursor, statement, parameters, context, many):
                statements.append(statement)

            event.listen(db.engine, "before_cursor_execute", record)
            try:
                self.get(path)
            finally:
                event.remove(db.engine, "before_cursor_execute", record)
            return len(statements)

        paths = ["data/projects", "data/projects/all", "data/projects/open"]
        # A first read fills the memoized lookups, which would offset the
        # queries made per project.
        for path in paths:
            self.get(path)
        one = {path: count_queries(path) for path in paths}
        for name in ["Second", "Third"]:
            self.generate_fixture_project(name=name)
        for path in paths:
            self.assertEqual(count_queries(path), one[path], path)
