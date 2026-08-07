import unittest

from zou.app import config
from zou.app.utils import redis


class RedisTestCase(unittest.TestCase):
    def setUp(self):
        # get_redis_url reads the store config at call time, and the
        # password branch has to be exercised on the real dict.
        self.password = config.KEY_VALUE_STORE.get("password")
        self.addCleanup(self.restore_password)

    def restore_password(self):
        config.KEY_VALUE_STORE["password"] = self.password

    def test_get_redis_url(self):
        db_index = 0
        config.KEY_VALUE_STORE["password"] = None
        self.assertEqual(
            redis.get_redis_url(db_index),
            f"redis://{config.KEY_VALUE_STORE['host']}"
            f":{config.KEY_VALUE_STORE['port']}/{db_index}",
        )
        config.KEY_VALUE_STORE["password"] = "password"
        self.assertEqual(
            redis.get_redis_url(db_index),
            f"redis://:{config.KEY_VALUE_STORE['password']}"
            f"@{config.KEY_VALUE_STORE['host']}"
            f":{config.KEY_VALUE_STORE['port']}/{db_index}",
        )
