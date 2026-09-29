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
