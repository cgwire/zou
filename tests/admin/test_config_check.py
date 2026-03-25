import orjson as json

from tests.base import ApiDBTestCase
from zou.app import config
from zou.app.stores import config_store

TEST_TOKEN = "test-admin-token"


class ConfigCheckTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self._original_token = config.ADMIN_TOKEN
        config.ADMIN_TOKEN = TEST_TOKEN

    def tearDown(self):
        config.ADMIN_TOKEN = self._original_token
        super().tearDown()

    def test_403_without_token(self):
        response = self.app.get("admin/config/check")
        self.assertEqual(response.status_code, 403)

    def test_403_with_wrong_token(self):
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": "Bearer wrong-token"},
        )
        self.assertEqual(response.status_code, 403)

    def test_403_with_malformed_header(self):
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": TEST_TOKEN},
        )
        self.assertEqual(response.status_code, 403)

    def test_403_when_admin_token_not_set(self):
        config.ADMIN_TOKEN = ""
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_200_with_correct_token(self):
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        for key in [
            "user_limit",
            "default_timezone",
            "default_locale",
            "nomad_host",
            "nomad_normalize_job",
            "nomad_playlist_job",
        ]:
            self.assertIn(key, data)
            self.assertIn("env", data[key])
            self.assertIn("redis", data[key])

        self.assertIn("active_users", data)

    def test_env_values_match_config(self):
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        data = json.loads(response.data)

        self.assertEqual(data["user_limit"]["env"], config.USER_LIMIT)
        self.assertEqual(
            data["default_timezone"]["env"], config.DEFAULT_TIMEZONE
        )
        self.assertEqual(data["default_locale"]["env"], config.DEFAULT_LOCALE)
        self.assertEqual(
            data["nomad_host"]["env"], config.JOB_QUEUE_NOMAD_HOST
        )

    def test_redis_values_after_sync(self):
        config_store.sync_config()
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        data = json.loads(response.data)

        self.assertEqual(int(data["user_limit"]["redis"]), config.USER_LIMIT)
        self.assertEqual(
            data["default_timezone"]["redis"], config.DEFAULT_TIMEZONE
        )
        self.assertEqual(
            data["default_locale"]["redis"], config.DEFAULT_LOCALE
        )

    def test_active_users_count(self):
        response = self.app.get(
            "admin/config/check",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        data = json.loads(response.data)

        self.assertIsInstance(data["active_users"], int)
        self.assertGreaterEqual(data["active_users"], 1)
