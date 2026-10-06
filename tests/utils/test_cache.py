import uuid
import unittest

from zou.app.utils import cache


class CacheTestCase(unittest.TestCase):
    __name__ = "test_handler"

    def setUp(self):
        super().setUp()
        global called
        self.called = 0

    @cache.memoize_function(50)
    def memoized_function(self, parameter):
        self.called = self.called + 1

    @cache.memoize_function(50)
    def memoized_function2(self, parameter):
        import random

        return parameter + str(random.randrange(1, 50))

    def test_memoize(self):
        result = self.memoized_function2("param1")
        result2 = self.memoized_function2("param1")
        result3 = self.memoized_function2("param2")

        self.assertEqual(result, result2)
        self.assertNotEqual(result, result3)

    @cache.memoize_function(50)
    def memoized_function3(self, entity_id):
        # A recomputed value must differ from the cached one: count the
        # calls, a random draw repeats one time in 49.
        self.called += 1
        return f"{entity_id}-{self.called}"

    def test_memoize_normalizes_uuid_arguments(self):
        entity_id = uuid.uuid4()
        result = self.memoized_function3(entity_id)
        result_str = self.memoized_function3(str(entity_id))
        self.assertEqual(result, result_str)

        cache.cache.delete_memoized(
            self.memoized_function3, self, str(entity_id)
        )
        result_after_str_invalidation = self.memoized_function3(entity_id)
        self.assertNotEqual(result, result_after_str_invalidation)

        cache.cache.delete_memoized(self.memoized_function3, self, entity_id)
        result_after_uuid_invalidation = self.memoized_function3(
            str(entity_id)
        )
        self.assertNotEqual(
            result_after_str_invalidation, result_after_uuid_invalidation
        )
