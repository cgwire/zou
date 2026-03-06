import os
import unittest

from zou.app.utils.env import envtobool, env_with_semicolon_to_list


class EnvTestCase(unittest.TestCase):
    def test_envtobool_true(self):
        os.environ["TEST_BOOL"] = "true"
        self.assertTrue(envtobool("TEST_BOOL"))

    def test_envtobool_false(self):
        os.environ["TEST_BOOL"] = "false"
        self.assertFalse(envtobool("TEST_BOOL"))

    def test_envtobool_default(self):
        os.environ.pop("TEST_BOOL", None)
        self.assertFalse(envtobool("TEST_BOOL"))
        self.assertTrue(envtobool("TEST_BOOL", default=True))

    def test_envtobool_invalid_raises(self):
        os.environ["TEST_BOOL"] = "maybe"
        with self.assertRaises(ValueError):
            envtobool("TEST_BOOL")

    def test_env_with_semicolon_to_list(self):
        os.environ["TEST_LIST"] = "a;b;c"
        self.assertEqual(env_with_semicolon_to_list("TEST_LIST"), ["a", "b", "c"])

    def test_env_with_semicolon_to_list_single(self):
        os.environ["TEST_LIST"] = "only"
        self.assertEqual(env_with_semicolon_to_list("TEST_LIST"), ["only"])

    def test_env_with_semicolon_to_list_default(self):
        os.environ.pop("TEST_LIST", None)
        self.assertEqual(env_with_semicolon_to_list("TEST_LIST"), [])
        self.assertEqual(
            env_with_semicolon_to_list("TEST_LIST", default=["x"]), ["x"]
        )
