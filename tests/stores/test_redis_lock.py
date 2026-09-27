from unittest import mock

import redis

from tests.base import ApiDBTestCase

from zou.app.stores import redis_lock


class RedisLockTestCase(ApiDBTestCase):
    def test_lock_is_exclusive_until_released(self):
        with redis_lock.with_lock("test-lock", wait_timeout=0.1) as acquired:
            self.assertTrue(acquired)
            with redis_lock.with_lock("test-lock", wait_timeout=0.1) as again:
                self.assertFalse(again)
        with redis_lock.with_lock("test-lock", wait_timeout=0.1) as after:
            self.assertTrue(after)

    def test_locks_on_other_keys_do_not_contend(self):
        with redis_lock.with_playlist_lock("a", wait_timeout=0.1) as first:
            with redis_lock.with_playlist_lock(
                "b", wait_timeout=0.1
            ) as second:
                self.assertTrue(first)
                self.assertTrue(second)

    def test_an_unreachable_redis_degrades_to_an_unlocked_run(self):
        # The lock used to open and ping a client on every call; the shared
        # client connects lazily, so the failure shows up on acquire.
        class Unreachable:
            def lock(self, *args, **kwargs):
                raise redis.ConnectionError("down")

        with mock.patch.object(
            redis_lock, "get_redis_client", return_value=Unreachable()
        ):
            with self.assertLogs(redis_lock.logger, level="WARNING"):
                with redis_lock.with_lock("test-lock") as acquired:
                    self.assertTrue(acquired)
