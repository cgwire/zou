import os
import subprocess
import sys
import unittest


class LazyAppTestCase(unittest.TestCase):
    """
    The default application must be built lazily: importing zou.app (or
    any submodule) stays side-effect free, and the first access to
    `zou.app.app` builds and caches it. Observed from a fresh
    interpreter because the suite's conftest already built the app in
    this process.
    """

    def test_importing_zou_app_does_not_build_the_app(self):
        code = (
            "import zou.app; "
            "assert 'app' not in vars(zou.app), 'import built the app'; "
            "from flask import Flask; "
            "assert isinstance(zou.app.app, Flask); "
            "assert 'app' in vars(zou.app), 'lazy build was not cached'"
        )
        env = dict(os.environ, SECRET_KEY="test-only")
        subprocess.run([sys.executable, "-c", code], check=True, env=env)
