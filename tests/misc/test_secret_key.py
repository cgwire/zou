import os
import subprocess
import sys
import unittest


class SecretKeyGuardTestCase(unittest.TestCase):
    """
    Zou refuses to serve HTTP with the public default SECRET_KEY (JWT
    forgery), but CLI commands must keep working with it. The guard fires
    at config import, so it is observed from fresh interpreters where
    neither pytest nor a caller has set the variable.
    """

    def _run(self, code):
        env = dict(os.environ)
        env.pop("SECRET_KEY", None)
        env.pop("DEBUG", None)
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            env=env,
        )

    def test_server_context_rejects_default_secret_key(self):
        result = self._run("import zou.app.config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"insecure default", result.stderr)

    def test_cli_context_allows_default_secret_key(self):
        result = self._run("import zou.cli; import zou.app.config")
        self.assertEqual(result.returncode, 0, result.stderr)
