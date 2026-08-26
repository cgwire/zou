from tests.base import ApiDBTestCase

from zou.app.services import notifications_service


class WithTasksConditionalGetTestCase(ApiDBTestCase):
    """
    The conditional GET contract of the with-tasks boards kitsu polls.
    The validator must move with everything the payload embeds: the
    entities themselves, their parents' names, the tasks and the
    caller's subscriptions.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot("SH01")
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.shot_task = self.generate_fixture_shot_task()
        self.shots_path = f"data/shots/with-tasks?project_id={self.project_id}"
        # First hits lazily create missing entity types, which moves the
        # fingerprint once: warm the boards up so the tests observe the
        # steady state, as production does.
        self.get_response(self.shots_path)
        self.get_response(
            f"data/assets/with-tasks?project_id={self.project_id}"
        )

    def get_response(self, path, headers=None):
        return self.app.get(
            path, headers={**self.base_headers, **(headers or {})}
        )

    def get_etag(self, path):
        response = self.get_response(path)
        self.assertEqual(response.status_code, 200)
        etag = response.headers.get("ETag")
        self.assertIsNotNone(etag)
        return etag

    def test_the_board_carries_a_validator_when_project_scoped(self):
        response = self.get_response(self.shots_path)
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.headers.get("ETag"))
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("private", cache_control)
        self.assertIn("no-cache", cache_control)
        unscoped = self.get_response("data/shots/with-tasks")
        self.assertIsNone(unscoped.headers.get("ETag"))

    def test_an_unchanged_board_answers_304(self):
        etag = self.get_etag(self.shots_path)
        second = self.get_response(
            self.shots_path, headers={"If-None-Match": etag}
        )
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.get_data(), b"")

    def test_a_parent_rename_invalidates_the_board(self):
        etag = self.get_etag(self.shots_path)
        self.sequence.update({"name": "SQ_RENAMED"})
        second = self.get_response(
            self.shots_path, headers={"If-None-Match": etag}
        )
        self.assertEqual(second.status_code, 200)

    def test_a_subscription_invalidates_the_board(self):
        etag = self.get_etag(self.shots_path)
        notifications_service.subscribe_to_task(
            self.user["id"], str(self.shot_task.id)
        )
        second = self.get_response(
            self.shots_path, headers={"If-None-Match": etag}
        )
        self.assertEqual(second.status_code, 200)

    def test_the_compact_board_honors_the_validator_too(self):
        path = f"{self.shots_path}&compact=true"
        etag = self.get_etag(path)
        second = self.get_response(path, headers={"If-None-Match": etag})
        self.assertEqual(second.status_code, 304)

    def test_the_assets_board_carries_the_same_contract(self):
        path = f"data/assets/with-tasks?project_id={self.project_id}"
        etag = self.get_etag(path)
        second = self.get_response(path, headers={"If-None-Match": etag})
        self.assertEqual(second.status_code, 304)
        self.asset.update({"name": "Zebra"})
        third = self.get_response(path, headers={"If-None-Match": etag})
        self.assertEqual(third.status_code, 200)
