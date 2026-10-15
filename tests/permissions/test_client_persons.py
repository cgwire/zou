from tests.base import ApiDBTestCase

from zou.app.services import projects_service

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
