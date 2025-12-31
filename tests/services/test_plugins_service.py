# -*- coding: UTF-8 -*-
import os
import tempfile
import shutil

from pathlib import Path
from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.plugin import Plugin
from zou.app.services import plugins_service
from zou.app.utils.plugins import PluginManifest


class PluginsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(PluginsServiceTestCase, self).setUp()
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_folder = Path(self.temp_dir) / "plugins"
        self.plugin_folder.mkdir(parents=True, exist_ok=True)

        self.original_plugin_folder = config.PLUGIN_FOLDER
        config.PLUGIN_FOLDER = str(self.plugin_folder)

    def tearDown(self):
        super(PluginsServiceTestCase, self).tearDown()
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

    def test_install_plugin_upgrade(self):
        existing_plugin = Plugin.create(
            plugin_id="test_plugin",
            name="Test Plugin",
            version="0.1.0",
            maintainer_name="Test Author",
            maintainer_email="test@example.com",
            license="MIT",
        )
        plugin_path = self._create_test_plugin("test_plugin", "0.2.0")
        result = plugins_service.install_plugin(str(plugin_path), force=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "0.2.0")
        plugin = Plugin.query.filter_by(plugin_id="test_plugin").first()
        self.assertEqual(plugin.version, "0.2.0")

    def test_install_plugin_same_version(self):
        existing_plugin = Plugin.create(
            plugin_id="test_plugin",
            name="Test Plugin",
            version="0.1.0",
            maintainer_name="Test Author",
            maintainer_email="test@example.com",
            license="MIT",
        )
        plugin_path = self._create_test_plugin("test_plugin", "0.1.0")
        result = plugins_service.install_plugin(str(plugin_path), force=True)
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], "0.1.0")

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
        plugin1 = Plugin.create(
            plugin_id="plugin1",
            name="Plugin 1",
            version="0.1.0",
            maintainer_name="Author 1",
            maintainer_email="author1@example.com",
            license="MIT",
        )
        plugin2 = Plugin.create(
            plugin_id="plugin2",
            name="Plugin 2",
            version="0.2.0",
            maintainer_name="Author 2",
            maintainer_email="author2@example.com",
            license="GPL-3.0-only",
        )

        plugins = plugins_service.get_plugins()

        self.assertEqual(len(plugins), 2)
        plugin_ids = [p["plugin_id"] for p in plugins]
        self.assertIn("plugin1", plugin_ids)
        self.assertIn("plugin2", plugin_ids)
