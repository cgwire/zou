from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.stores import config_store
from zou.app.services import persons_service


class ConfigStoreTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        for key in self._all_keys():
            config_store.config_store.delete(key)

    def tearDown(self):
        for key in self._all_keys():
            config_store.config_store.delete(key)
        super().tearDown()

    @staticmethod
    def _all_keys():
        return [
            config_store.USER_LIMIT_KEY,
            config_store.DEFAULT_TIMEZONE_KEY,
            config_store.DEFAULT_LOCALE_KEY,
            config_store.NOMAD_HOST_KEY,
            config_store.NOMAD_NORMALIZE_JOB_KEY,
            config_store.NOMAD_PLAYLIST_JOB_KEY,
        ]

    # --- USER_LIMIT ---

    def test_get_user_limit_fallback(self):
        """When Redis has no value, fall back to config.USER_LIMIT."""
        self.assertEqual(config_store.get_user_limit(), config.USER_LIMIT)

    def test_get_user_limit_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 42)
        self.assertEqual(config_store.get_user_limit(), 42)

    def test_persons_service_get_user_limit(self):
        """persons_service.get_user_limit reads from Redis."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 77)
        self.assertEqual(persons_service.get_user_limit(), 77)

    def test_is_user_limit_reached_with_redis(self):
        """is_user_limit_reached uses the Redis value."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 1)
        self.assertTrue(persons_service.is_user_limit_reached())
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 1000)
        self.assertFalse(persons_service.is_user_limit_reached())

    def test_create_person_blocked_by_redis_limit(self):
        """POST /data/persons is blocked when Redis limit is reached."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 1)
        data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test.limit@gmail.com",
        }
        resp = self.post("data/persons", data, 400)
        self.assertEqual(resp["data"]["limit"], 1)

    def test_create_person_allowed_by_redis_limit(self):
        """POST /data/persons succeeds when Redis limit is high."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 1000)
        data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test.limit@gmail.com",
        }
        resp = self.post("data/persons", data, 201)
        self.assertEqual(resp["first_name"], "Test")

    def test_context_returns_redis_limit(self):
        """GET /data/user/context returns the Redis user limit."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 55)
        context = self.get("data/user/context")
        self.assertEqual(context["user_limit"], 55)

    # --- DEFAULT_TIMEZONE ---

    def test_get_default_timezone_fallback(self):
        """When Redis has no value, fall back to config."""
        self.assertEqual(
            config_store.get_default_timezone(),
            config.DEFAULT_TIMEZONE,
        )

    def test_get_default_timezone_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(
            config_store.DEFAULT_TIMEZONE_KEY, "America/New_York"
        )
        self.assertEqual(
            config_store.get_default_timezone(), "America/New_York"
        )

    def test_persons_service_get_default_timezone(self):
        """persons_service.get_default_timezone reads from Redis."""
        config_store.config_store.set(
            config_store.DEFAULT_TIMEZONE_KEY, "Asia/Tokyo"
        )
        self.assertEqual(persons_service.get_default_timezone(), "Asia/Tokyo")

    def test_config_returns_redis_timezone(self):
        """GET /config returns the Redis default_timezone."""
        config_store.config_store.set(
            config_store.DEFAULT_TIMEZONE_KEY, "US/Eastern"
        )
        conf = self.get("config")
        self.assertEqual(conf["default_timezone"], "US/Eastern")

    # --- DEFAULT_LOCALE ---

    def test_get_default_locale_fallback(self):
        """When Redis has no value, fall back to config."""
        self.assertEqual(
            config_store.get_default_locale(),
            config.DEFAULT_LOCALE,
        )

    def test_get_default_locale_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(config_store.DEFAULT_LOCALE_KEY, "fr_FR")
        self.assertEqual(config_store.get_default_locale(), "fr_FR")

    def test_persons_service_get_default_locale(self):
        """persons_service.get_default_locale reads from Redis."""
        config_store.config_store.set(config_store.DEFAULT_LOCALE_KEY, "de_DE")
        self.assertEqual(persons_service.get_default_locale(), "de_DE")

    def test_config_returns_redis_locale(self):
        """GET /config returns the Redis default_locale."""
        config_store.config_store.set(config_store.DEFAULT_LOCALE_KEY, "ja_JP")
        conf = self.get("config")
        self.assertEqual(conf["default_locale"], "ja_JP")

    # --- NOMAD_HOST ---

    def test_get_nomad_host_fallback(self):
        """When Redis has no value, fall back to config."""
        self.assertEqual(
            config_store.get_nomad_host(),
            config.JOB_QUEUE_NOMAD_HOST,
        )

    def test_get_nomad_host_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(
            config_store.NOMAD_HOST_KEY, "nomad.example.com"
        )
        self.assertEqual(config_store.get_nomad_host(), "nomad.example.com")

    # --- NOMAD_NORMALIZE_JOB ---

    def test_get_nomad_normalize_job_fallback(self):
        """When Redis has no value, fall back to config."""
        self.assertEqual(
            config_store.get_nomad_normalize_job(),
            config.JOB_QUEUE_NOMAD_NORMALIZE_JOB,
        )

    def test_get_nomad_normalize_job_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(
            config_store.NOMAD_NORMALIZE_JOB_KEY, "zou-norm-v2"
        )
        self.assertEqual(config_store.get_nomad_normalize_job(), "zou-norm-v2")

    # --- NOMAD_PLAYLIST_JOB ---

    def test_get_nomad_playlist_job_fallback(self):
        """When Redis has no value, fall back to config."""
        self.assertEqual(
            config_store.get_nomad_playlist_job(),
            config.JOB_QUEUE_NOMAD_PLAYLIST_JOB,
        )

    def test_get_nomad_playlist_job_from_redis(self):
        """When Redis has a value, return it."""
        config_store.config_store.set(
            config_store.NOMAD_PLAYLIST_JOB_KEY, "zou-playlist-v2"
        )
        self.assertEqual(
            config_store.get_nomad_playlist_job(), "zou-playlist-v2"
        )

    # --- sync_config ---

    def test_sync_config_sets_all_values(self):
        """sync_config pushes all env var values to Redis."""
        values = config_store.sync_config()
        self.assertEqual(values["user_limit"], config.USER_LIMIT)
        self.assertEqual(values["default_timezone"], config.DEFAULT_TIMEZONE)
        self.assertEqual(values["default_locale"], config.DEFAULT_LOCALE)
        self.assertEqual(values["nomad_host"], config.JOB_QUEUE_NOMAD_HOST)
        self.assertEqual(
            values["nomad_normalize_job"],
            config.JOB_QUEUE_NOMAD_NORMALIZE_JOB,
        )
        self.assertEqual(
            values["nomad_playlist_job"],
            config.JOB_QUEUE_NOMAD_PLAYLIST_JOB,
        )
        self.assertEqual(
            config_store.config_store.get(config_store.USER_LIMIT_KEY),
            str(config.USER_LIMIT),
        )
        self.assertEqual(
            config_store.config_store.get(config_store.DEFAULT_TIMEZONE_KEY),
            config.DEFAULT_TIMEZONE,
        )
        self.assertEqual(
            config_store.config_store.get(config_store.DEFAULT_LOCALE_KEY),
            config.DEFAULT_LOCALE,
        )
        self.assertEqual(
            config_store.config_store.get(config_store.NOMAD_HOST_KEY),
            config.JOB_QUEUE_NOMAD_HOST,
        )
        self.assertEqual(
            config_store.config_store.get(
                config_store.NOMAD_NORMALIZE_JOB_KEY
            ),
            config.JOB_QUEUE_NOMAD_NORMALIZE_JOB,
        )
        self.assertEqual(
            config_store.config_store.get(config_store.NOMAD_PLAYLIST_JOB_KEY),
            config.JOB_QUEUE_NOMAD_PLAYLIST_JOB,
        )

    def test_sync_config_updates_when_different(self):
        """sync_config overwrites Redis when values differ."""
        config_store.config_store.set(config_store.USER_LIMIT_KEY, 999)
        config_store.config_store.set(
            config_store.DEFAULT_TIMEZONE_KEY, "Old/Zone"
        )
        config_store.config_store.set(config_store.NOMAD_HOST_KEY, "old-host")
        original_limit = config.USER_LIMIT
        original_tz = config.DEFAULT_TIMEZONE
        original_host = config.JOB_QUEUE_NOMAD_HOST
        config.USER_LIMIT = 50
        config.DEFAULT_TIMEZONE = "UTC"
        config.JOB_QUEUE_NOMAD_HOST = "new-nomad-host"
        try:
            config_store.sync_config()
            self.assertEqual(config_store.get_user_limit(), 50)
            self.assertEqual(config_store.get_default_timezone(), "UTC")
            self.assertEqual(config_store.get_nomad_host(), "new-nomad-host")
        finally:
            config.USER_LIMIT = original_limit
            config.DEFAULT_TIMEZONE = original_tz
            config.JOB_QUEUE_NOMAD_HOST = original_host
