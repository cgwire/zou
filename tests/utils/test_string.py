import unittest

from zou.app.utils.string import strtobool


class StringTestCase(unittest.TestCase):
    def test_strtobool_true_values(self):
        for val in ("y", "yes", "t", "true", "on", "1"):
            self.assertTrue(strtobool(val))
            self.assertTrue(strtobool(val.upper()))

    def test_strtobool_false_values(self):
        for val in ("n", "no", "f", "false", "off", "0"):
            self.assertFalse(strtobool(val))
            self.assertFalse(strtobool(val.upper()))

    def test_strtobool_bool_passthrough(self):
        self.assertTrue(strtobool(True))
        self.assertFalse(strtobool(False))

    def test_strtobool_int_passthrough(self):
        self.assertTrue(strtobool(1))
        self.assertFalse(strtobool(0))

    def test_strtobool_invalid_raises(self):
        with self.assertRaises(ValueError):
            strtobool("maybe")
        with self.assertRaises(ValueError):
            strtobool("")
