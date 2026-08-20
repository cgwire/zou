import os
import subprocess
import sys
import unittest


class PreviewSourceSettingsGuardTestCase(unittest.TestCase):
    """
    Skipping the normalization already keeps the source movie as the
    preview, so combining it with PREVIEW_SAVE_SOURCE_FILE describes two
    conflicting layouts for the same bytes. The guard fires at config
    import, hence the fresh interpreters.
    """

    def _run(self, **settings):
        env = dict(os.environ)
        env["SECRET_KEY"] = "a-secret-key-for-this-test"
        for name in [
            "PREVIEW_SAVE_SOURCE_FILE",
            "SKIP_NORMALIZATION_FULL",
            "SKIP_NORMALIZATION_HIGHDEF",
        ]:
            env.pop(name, None)
        env.update(settings)
        return subprocess.run(
            [sys.executable, "-c", "import zou.app.config"],
            capture_output=True,
            env=env,
        )

    def test_saving_the_source_and_skipping_everything_is_refused(self):
        result = self._run(
            PREVIEW_SAVE_SOURCE_FILE="1", SKIP_NORMALIZATION_FULL="1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"cannot be combined", result.stderr)

    def test_saving_the_source_and_skipping_the_high_def_is_refused(self):
        result = self._run(
            PREVIEW_SAVE_SOURCE_FILE="1", SKIP_NORMALIZATION_HIGHDEF="1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"cannot be combined", result.stderr)

    def test_each_setting_on_its_own_is_fine(self):
        for settings in [
            {"PREVIEW_SAVE_SOURCE_FILE": "1"},
            {"SKIP_NORMALIZATION_FULL": "1"},
            {"SKIP_NORMALIZATION_HIGHDEF": "1"},
        ]:
            with self.subTest(settings=settings):
                result = self._run(**settings)
                self.assertEqual(result.returncode, 0, result.stderr)
