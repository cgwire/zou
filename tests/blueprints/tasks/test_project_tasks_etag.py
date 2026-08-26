from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class ProjectTasksConditionalGetTestCase(ApiDBTestCase):
    """
    The conditional GET contract of the project tasks listing: kitsu
    polls it, so an unchanged project must answer 304 from the freshness
    signal alone, and the validator must be bound to the caller so a
    role change or an account switch never validates someone else's
    payload.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.task = self.generate_fixture_task()
        self.path = f"/data/projects/{self.project.id}/tasks"

    def get_response(self, headers=None):
        return self.app.get(
            self.path, headers={**self.base_headers, **(headers or {})}
        )

    def test_the_listing_carries_a_validator(self):
        response = self.get_response()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.headers.get("ETag"))
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("private", cache_control)
        self.assertIn("no-cache", cache_control)

    def test_an_unchanged_project_answers_304(self):
        first = self.get_response()
        etag = first.headers.get("ETag")
        self.assertIsNotNone(etag)
        second = self.get_response(headers={"If-None-Match": etag})
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.get_data(), b"")

    def test_a_task_change_invalidates_the_etag(self):
        first = self.get_response()
        etag = first.headers.get("ETag")
        self.assertIsNotNone(etag)
        self.task.update({"priority": 3})
        second = self.get_response(headers={"If-None-Match": etag})
        self.assertEqual(second.status_code, 200)

    def test_the_validator_is_bound_to_the_caller(self):
        first = self.get_response()
        etag = first.headers.get("ETag")
        self.assertIsNotNone(etag)
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            str(self.project.id), self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        second = self.get_response(headers={"If-None-Match": etag})
        self.assertEqual(second.status_code, 200)
