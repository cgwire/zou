import hashlib
import unittest

from zou.app.utils.string import mask_secret, strtobool


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

    def test_mask_secret_keeps_the_ends_and_a_fingerprint(self):
        token = "xoxb-1234567890-secretsecret-abcd"
        fingerprint = hashlib.sha256(token.encode()).hexdigest()[:8]
        masked = mask_secret(token)
        self.assertEqual(masked, f"xoxb********abcd (sha256:{fingerprint})")
        self.assertNotIn("secret", masked)

    def test_mask_secret_hides_short_values_entirely(self):
        masked = mask_secret("short-token")
        self.assertTrue(masked.startswith("******** (sha256:"))
        self.assertNotIn("short", masked)

    def test_mask_secret_keeps_only_the_host_of_a_url(self):
        webhook = "https://user:pw@mm.example.com:8065/hooks/abcdef123456"
        masked = mask_secret(webhook)
        self.assertTrue(
            masked.startswith("https://mm.example.com:8065/******** (sha256:")
        )
        self.assertNotIn("abcdef", masked)
        self.assertNotIn("pw", masked)

    def test_mask_secret_passes_empty_values_through(self):
        self.assertIsNone(mask_secret(None))
        self.assertEqual(mask_secret(""), "")
