import unittest

import pytest

from zou.app.utils import shell


class ShellTestCase(unittest.TestCase):
    def test_run_command(self):
        out = shell.run_command(["ls"])
        self.assertTrue(len(out) > 0)
        with pytest.raises(shell.ShellCommandFailed):
            shell.run_command(["nonexist"])
