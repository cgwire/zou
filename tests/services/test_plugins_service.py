# -*- coding: UTF-8 -*-
import os
import tempfile
import shutil
import zipfile

from pathlib import Path
from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.plugin import Plugin
from zou.app.services import plugins_service
from zou.app.utils.plugins import PluginManifest


class PluginsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_folder = Path(self.temp_dir) / "plugins"
        self.plugin_folder.mkdir(parents=True, exist_ok=True)

        self.original_plugin_folder = config.PLUGIN_FOLDER
        config.PLUGIN_FOLDER = str(self.plugin_folder)

    def tearDown(self):
        super().tearDown()
        config.PLUGIN_FOLDER = self.original_plugin_folder
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _create_test_plugin(self, plugin_id="test_plugin", version="0.1.0"):
        plugin_template_path = (
            Path(__file__).parent.parent.parent / "zou" / "plugin_template"
        )
        plugin_path = Path(self.temp_dir) / plugin_id

        shutil.copytree(plugin_template_path, plugin_path)
        manifest = PluginManifest.from_file(plugin_path / "manifest.toml")
        manifest.id = plugin_id
        manifest.name = "Test Plugin"
        manifest.description = "A test plugin"
        manifest.version = version
        manifest.maintainer = "Test Author <test@example.com>"
        manifest.website = "https://example.com"
        manifest.license = "MIT"
        manifest.validate()
        manifest.write_to_path(plugin_path)

        return plugin_path

    def a_plugin_row(self, plugin_id, version="0.1.0", **overrides):
        """
        A plugin already recorded in the database, without any files.
        """
        return Plugin.create(
            plugin_id=plugin_id,
            name=f"Plugin {plugin_id}",
            version=version,
            maintainer_name="Test Author",
            maintainer_email="test@example.com",
            **{"license": "MIT", **overrides},
        )

    def test_install_plugin_new(self):
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")

        result = plugins_service.install_plugin(str(plugin_path))

        self.assertIsNotNone(result)
        self.assertEqual(result["plugin_id"], "test_plugin")
        self.assertEqual(result["name"], "Test Plugin")
        self.assertEqual(result["version"], "0.1.0")

        plugin = Plugin.query.filter_by(plugin_id="test_plugin").first()
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.version, "0.1.0")

        installed_path = self.plugin_folder / "test_plugin"
        self.assertTrue(installed_path.exists())
        self.assertTrue((installed_path / "manifest.toml").exists())

    def test_install_plugin_keeps_existing_loggers_enabled(self):
        from zou.app import app

        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")
        plugins_service.install_plugin(str(plugin_path))
        self.assertFalse(app.logger.disabled)

    def test_install_plugin_upgrade(self):
        self.a_plugin_row("test_plugin", "0.1.0")
        plugin_path = self._create_test_plugin("test_plugin", "0.2.0")

        result = plugins_service.install_plugin(str(plugin_path), force=True)

        self.assertEqual(result["version"], "0.2.0")
        plugin = Plugin.query.filter_by(plugin_id="test_plugin").first()
        self.assertEqual(plugin.version, "0.2.0")

    def test_installing_an_older_version_warns_and_still_installs(self):
        """
        Without force, a version that is not newer only draws a warning: the
        install goes through and the row takes the older version. Worth
        stating plainly, the message reads like a refusal.
        """
        self.a_plugin_row("test_plugin", "0.2.0")
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")

        result = plugins_service.install_plugin(str(plugin_path))

        self.assertEqual(result["version"], "0.1.0")
        plugin = Plugin.query.filter_by(plugin_id="test_plugin").first()
        self.assertEqual(plugin.version, "0.1.0")

    @patch("zou.app.services.plugins_service.download_zip_url")
    def test_install_plugin_from_zip_url(self, mock_download):
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")

        zip_path = Path(self.temp_dir) / "download" / "plugin.zip"
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w") as zf:
            for file in plugin_path.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(plugin_path))

        mock_download.return_value = zip_path

        url = (
            "https://github.com/org/repo/releases/"
            "download/v0.1.0/test_plugin.zip"
        )
        result = plugins_service.install_plugin(url)

        self.assertIsNotNone(result)
        self.assertEqual(result["plugin_id"], "test_plugin")
        self.assertEqual(result["version"], "0.1.0")
        mock_download.assert_called_once_with(url)

        installed_path = self.plugin_folder / "test_plugin"
        self.assertTrue(installed_path.exists())
        self.assertTrue((installed_path / "manifest.toml").exists())

    @patch("zou.app.services.plugins_service.clone_git_repo")
    def test_install_plugin_from_git_url(self, mock_clone):
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")
        clone_root = Path(self.temp_dir) / "clone"
        clone_root.mkdir(parents=True, exist_ok=True)
        cloned = clone_root / "test_plugin"
        shutil.copytree(plugin_path, cloned)
        mock_clone.return_value = cloned

        url = "git@github.com:org/repo.git"
        result = plugins_service.install_plugin(url)

        self.assertEqual(result["plugin_id"], "test_plugin")
        mock_clone.assert_called_once_with(url)
        self.assertTrue((self.plugin_folder / "test_plugin").exists())
        # What was cloned is a working copy: it goes when the install ends.
        self.assertFalse(clone_root.exists())

    def test_install_plugin_nonexistent_path(self):
        with self.assertRaises(FileNotFoundError):
            plugins_service.install_plugin("/nonexistent/path")

    def test_uninstall_plugin(self):
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")
        plugins_service.install_plugin(str(plugin_path))

        plugin = Plugin.query.filter_by(plugin_id="test_plugin").first()
        self.assertIsNotNone(plugin)

        installed_path = self.plugin_folder / "test_plugin"
        self.assertTrue(installed_path.exists())

        result = plugins_service.uninstall_plugin("test_plugin")

        self.assertTrue(result)

        deleted_plugin = Plugin.query.filter_by(
            plugin_id="test_plugin"
        ).first()
        self.assertIsNone(deleted_plugin)
        self.assertFalse(installed_path.exists())

    def test_uninstall_plugin_not_installed(self):
        with self.assertRaises(ValueError) as context:
            plugins_service.uninstall_plugin("nonexistent_plugin")
        self.assertIn("Invalid plugin path", str(context.exception))

    def test_get_plugins(self):
        self.assertEqual(plugins_service.get_plugins(), [])
        self.a_plugin_row("plugin1")
        self.a_plugin_row("plugin2", "0.2.0", license="GPL-3.0-only")

        plugins = plugins_service.get_plugins()

        self.assertEqual(
            sorted(plugin["plugin_id"] for plugin in plugins),
            ["plugin1", "plugin2"],
        )
