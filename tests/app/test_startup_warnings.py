import unittest

from unittest.mock import MagicMock, patch

from zou.app import warn_about_overridden_settings


class OverriddenSettingsWarningTestCase(unittest.TestCase):
    """
    A remote setup uploads the source movie whatever
    PREVIEW_SAVE_SOURCE_FILE says: say so rather than letting the setting
    read as being in effect.
    """

    def warn(self, is_remote, save_source_file):
        app = MagicMock()
        config_object = MagicMock()
        config_object.PREVIEW_SAVE_SOURCE_FILE = save_source_file
        with patch(
            "zou.app.services.preview_files_service"
            ".is_remote_normalization_enabled",
            return_value=is_remote,
        ):
            warn_about_overridden_settings(app, config_object)
        return app.logger.warning.call_args

    def test_remote_setup_without_the_setting_warns(self):
        call = self.warn(is_remote=True, save_source_file=False)
        self.assertIsNotNone(call)
        self.assertIn("PREVIEW_SAVE_SOURCE_FILE", call.args[0])

    def test_nothing_is_said_when_the_setting_is_in_effect(self):
        self.assertIsNone(self.warn(is_remote=True, save_source_file=True))
        self.assertIsNone(self.warn(is_remote=False, save_source_file=False))

    def test_an_unreachable_redis_does_not_break_the_boot(self):
        app = MagicMock()
        config_object = MagicMock()
        config_object.PREVIEW_SAVE_SOURCE_FILE = False
        with patch(
            "zou.app.services.preview_files_service"
            ".is_remote_normalization_enabled",
            side_effect=ConnectionError("redis is down"),
        ):
            warn_about_overridden_settings(app, config_object)
        app.logger.warning.assert_not_called()
