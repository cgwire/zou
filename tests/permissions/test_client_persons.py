from unittest import mock

from tests.base import ApiDBTestCase
from zou.app.services import index_service, persons_service, projects_service

CLIENT_PERSON_KEYS = {
    "id",
    "type",
    "first_name",
    "last_name",
    "full_name",
    "has_avatar",
    "active",
    "role",
    "is_bot",
}


class ClientPersonsTestCase(ApiDBTestCase):
    """
    A client meets the people of the productions shared with them, by
    name and avatar, and nobody else of the studio.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_client()
        self.project_id = str(self.project.id)
        projects_service.add_team_member(self.project_id, self.person.id)
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.team_ids = {str(self.person.id), self.user_client["id"]}

    def assert_client_persons(self, persons):
        self.assertEqual({person["id"] for person in persons}, self.team_ids)
        for person in persons:
            self.assertEqual(set(person.keys()), CLIENT_PERSON_KEYS)

    def test_persons_listing(self):
        persons = self.get("data/persons?relations=true&is_guest=false")
        self.assertIn("departments", persons[0])
        self.assertGreater(len(persons), 2)
        self.log_in_client()
        self.assert_client_persons(
            self.get("data/persons?relations=true&is_guest=false")
        )

    def test_paginated_persons_listing(self):
        self.log_in_client()
        result = self.get("data/persons?page=1")
        self.assertEqual(result["total"], len(self.team_ids))
        self.assert_client_persons(result["data"])

    def test_paginated_persons_count_the_team_only(self):
        path = (
            "data/persons?first_name=John"
            f"&last_name={self.user_cg_artist['last_name']}&page="
        )
        self.assertEqual(self.get(f"{path}1")["total"], 1)
        self.log_in_client()
        for page in (0, 1):
            self.assertEqual(self.get(f"{path}{page}")["total"], 0)

    def test_user_context(self):
        self.log_in_client()
        self.assert_client_persons(self.get("data/user/context")["persons"])

    def test_team(self):
        self.log_in_client()
        team = self.get(f"data/projects/{self.project_id}/team")
        self.assertEqual({person["id"] for person in team}, self.team_ids)
        for person in team:
            self.assertEqual(
                set(person.keys()), CLIENT_PERSON_KEYS | {"project_role"}
            )

    def test_person_detail(self):
        self.log_in_client()
        person = self.get(f"data/persons/{self.person.id}")
        self.assertEqual(set(person.keys()), CLIENT_PERSON_KEYS)
        self.get(f"data/persons/{self.user_cg_artist['id']}", 403)

    def test_department_members(self):
        """
        A client reads nothing of how the studio is organized: not even the
        departments of their own team.
        """
        self.generate_fixture_department()
        department_id = str(self.department.id)
        persons_service.add_to_department(department_id, str(self.person.id))
        path = f"data/departments/{department_id}/persons"

        self.log_in_cg_artist()
        members = self.get(path)
        self.assertEqual(
            [member["id"] for member in members], [str(self.person.id)]
        )
        self.log_in_client()
        self.get(path, 403)

    def test_persons_filters(self):
        """
        A client filters on the fields of present_client only, plus is_guest.
        """
        self.generate_fixture_department()
        department_id = str(self.department.id)
        persons_service.add_to_department(department_id, str(self.person.id))

        self.log_in_client()
        self.get(f"data/persons?departments={department_id}", 400)
        self.get(f"data/persons?email={self.person.email}", 400)

    def test_person_search(self):
        """
        The person index cannot be narrowed to the teams a client meets, so
        it answered with anyone of the studio, teammates included, as
        present_minimal. Kitsu offers clients no search: they get the people
        of their productions with their context.
        """
        body = {"query": "john", "index_names": ["persons"]}
        hits = [
            (self.user_cg_artist["id"], ["john"]),
            (str(self.person.id), ["john"]),
        ]
        with mock.patch.object(
            index_service, "get_person_index", return_value=None
        ), mock.patch("zou.app.indexer.indexing.search", return_value=hits):
            self.log_in_cg_artist()
            found = self.post("data/search", body, 200)["persons"]
            self.assertEqual(
                [person["id"] for person in found],
                [self.user_cg_artist["id"], str(self.person.id)],
            )
            self.log_in_client()
            self.assertEqual(
                self.post("data/search", body, 200)["persons"], []
            )
