# -*- coding: UTF-8 -*-
import os
import tempfile
import shutil
import zipfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock, call

from tests.base import ApiDBTestCase

from zou.app import app, config
from zou.app.utils.plugins import (
    PluginManifest,
    install_plugin_files,
    uninstall_plugin_files,
    clone_git_repo,
    create_plugin_package,
    create_plugin_skeleton,
    add_static_routes,
)


class PluginManifestTestCase(ApiDBTestCase):
    def setUp(self):
        super(PluginManifestTestCase, self).setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        super(PluginManifestTestCase, self).tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_plugin_manifest_from_file(self):
        manifest_path = Path(self.temp_dir) / "manifest.toml"
        manifest_content = '''id = "test_plugin"
name = "Test Plugin"
description = "A test plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
website = "https://example.com"
license = "MIT"
frontend_project_enabled = false
frontend_studio_enabled = false
'''
        manifest_path.write_text(manifest_content)

        manifest = PluginManifest.from_file(manifest_path)

        self.assertEqual(manifest["id"], "test_plugin")
        self.assertEqual(manifest["name"], "Test Plugin")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["license"], "MIT")

    def test_plugin_manifest_from_plugin_path_directory(self):
        plugin_dir = Path(self.temp_dir) / "test_plugin"
        plugin_dir.mkdir()

        manifest_path = plugin_dir / "manifest.toml"
        manifest_content = '''id = "test_plugin"
name = "Test Plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
license = "MIT"
'''
        manifest_path.write_text(manifest_content)

        manifest = PluginManifest.from_plugin_path(plugin_dir)

        self.assertEqual(manifest["id"], "test_plugin")
        self.assertEqual(manifest["name"], "Test Plugin")

    def test_plugin_manifest_from_plugin_path_zip(self):
        plugin_dir = Path(self.temp_dir) / "test_plugin"
        plugin_dir.mkdir()

        manifest_path = plugin_dir / "manifest.toml"
        manifest_content = '''id = "test_plugin"
name = "Test Plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
license = "MIT"
'''
        manifest_path.write_text(manifest_content)

        zip_path = Path(self.temp_dir) / "test_plugin.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(manifest_path, "manifest.toml")

        manifest = PluginManifest.from_plugin_path(zip_path)

        self.assertEqual(manifest["id"], "test_plugin")
        self.assertEqual(manifest["name"], "Test Plugin")

    def test_plugin_manifest_from_plugin_path_invalid(self):
        """Test creating PluginManifest from invalid path"""
        invalid_path = Path(self.temp_dir) / "invalid.txt"
        invalid_path.write_text("not a plugin")

        with self.assertRaises(ValueError) as context:
            PluginManifest.from_plugin_path(invalid_path)

        self.assertIn("Invalid plugin path", str(context.exception))

    def test_plugin_manifest_validate_version(self):
        """Test that manifest validates version format"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "invalid-version",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT"
        }

        with self.assertRaises(Exception):  # semver will raise an exception
            PluginManifest(manifest_data)

    def test_plugin_manifest_validate_license(self):
        """Test that manifest validates license"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "INVALID-LICENSE"
        }

        with self.assertRaises(KeyError):
            PluginManifest(manifest_data)

    def test_plugin_manifest_validate_maintainer(self):
        """Test that manifest parses maintainer email"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT"
        }

        manifest = PluginManifest(manifest_data)

        self.assertEqual(manifest.data.get("maintainer_name"), "Test Author")
        self.assertEqual(manifest.data.get("maintainer_email"), "test@example.com")

    def test_plugin_manifest_to_model_dict(self):
        """Test converting manifest to model dictionary"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "description": "A test plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "website": "https://example.com",
            "license": "MIT",
            "frontend_project_enabled": True,
            "frontend_studio_enabled": False,
            "icon": "test-icon"
        }

        manifest = PluginManifest(manifest_data)
        model_dict = manifest.to_model_dict()

        self.assertEqual(model_dict["plugin_id"], "test_plugin")
        self.assertEqual(model_dict["name"], "Test Plugin")
        self.assertEqual(model_dict["version"], "0.1.0")
        self.assertEqual(model_dict["license"], "MIT")
        self.assertTrue(model_dict["frontend_project_enabled"])
        self.assertFalse(model_dict["frontend_studio_enabled"])
        self.assertEqual(model_dict["icon"], "test-icon")

    def test_plugin_manifest_write_to_path(self):
        """Test writing manifest to a path"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT"
        }

        manifest = PluginManifest(manifest_data)
        output_path = Path(self.temp_dir) / "output"
        output_path.mkdir()

        manifest.write_to_path(output_path)

        written_manifest = PluginManifest.from_file(output_path / "manifest.toml")
        self.assertEqual(written_manifest["id"], "test_plugin")
        self.assertEqual(written_manifest["name"], "Test Plugin")


class PluginFilesTestCase(ApiDBTestCase):
    def setUp(self):
        super(PluginFilesTestCase, self).setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        super(PluginFilesTestCase, self).tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_install_plugin_files_from_directory(self):
        source_dir = Path(self.temp_dir) / "source"
        source_dir.mkdir()

        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")
        subdir = source_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        install_path = Path(self.temp_dir) / "install"

        result = install_plugin_files(source_dir, install_path)

        self.assertEqual(result, install_path)
        self.assertTrue((install_path / "file1.txt").exists())
        self.assertTrue((install_path / "file2.txt").exists())
        self.assertTrue((install_path / "subdir" / "file3.txt").exists())

        self.assertEqual((install_path / "file1.txt").read_text(), "content1")

    def test_install_plugin_files_from_zip(self):
        source_dir = Path(self.temp_dir) / "source"
        source_dir.mkdir()

        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        zip_path = Path(self.temp_dir) / "plugin.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(source_dir / "file1.txt", "file1.txt")
            zf.write(source_dir / "file2.txt", "file2.txt")

        install_path = Path(self.temp_dir) / "install"

        result = install_plugin_files(zip_path, install_path)

        self.assertEqual(result, install_path)
        self.assertTrue((install_path / "file1.txt").exists())
        self.assertTrue((install_path / "file2.txt").exists())

    def test_install_plugin_files_invalid_path(self):
        invalid_path = Path(self.temp_dir) / "invalid.txt"
        invalid_path.write_text("not a directory or zip")

        install_path = Path(self.temp_dir) / "install"

        with self.assertRaises(ValueError) as context:
            install_plugin_files(invalid_path, install_path)

        self.assertIn("not a valid zip file or a directory", str(context.exception))

    def test_uninstall_plugin_files(self):
        plugin_path = Path(self.temp_dir) / "plugin"
        plugin_path.mkdir()
        (plugin_path / "file1.txt").write_text("content1")

        result = uninstall_plugin_files(plugin_path)

        self.assertTrue(result)
        self.assertFalse(plugin_path.exists())

    def test_uninstall_plugin_files_nonexistent(self):
        """Test uninstalling non-existent plugin files"""
        nonexistent_path = Path(self.temp_dir) / "nonexistent"

        result = uninstall_plugin_files(nonexistent_path)

        self.assertFalse(result)


class PluginPackageTestCase(ApiDBTestCase):
    def setUp(self):
        super(PluginPackageTestCase, self).setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        super(PluginPackageTestCase, self).tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_plugin_package(self):
        """Test creating a plugin package"""
        plugin_dir = Path(self.temp_dir) / "test_plugin"
        plugin_dir.mkdir()

        manifest_path = plugin_dir / "manifest.toml"
        manifest_content = '''id = "test_plugin"
name = "Test Plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
license = "MIT"
'''
        manifest_path.write_text(manifest_content)
        (plugin_dir / "file1.txt").write_text("content1")

        output_path = Path(self.temp_dir) / "output.zip"

        result = create_plugin_package(plugin_dir, output_path)

        self.assertTrue(result.exists())
        self.assertTrue(result.suffix == ".zip")

        with zipfile.ZipFile(result, 'r') as zf:
            files = zf.namelist()
            self.assertIn("manifest.toml", files)
            self.assertIn("file1.txt", files)


class PluginSkeletonTestCase(ApiDBTestCase):
    def setUp(self):
        super(PluginSkeletonTestCase, self).setUp()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        super(PluginSkeletonTestCase, self).tearDown()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_plugin_skeleton(self):
        output_dir = Path(self.temp_dir) / "output"
        output_dir.mkdir()

        result = create_plugin_skeleton(
            output_dir,
            id="test_plugin",
            name="Test Plugin",
            description="A test plugin",
            version="0.2.0",
            maintainer="Test Author <test@example.com>",
            website="https://example.com",
            license="MIT",
            icon="test-icon"
        )

        self.assertTrue(result.exists())
        self.assertEqual(result.name, "test_plugin")

        manifest = PluginManifest.from_file(result / "manifest.toml")
        self.assertEqual(manifest.id, "test_plugin")
        self.assertEqual(manifest.name, "Test Plugin")
        self.assertEqual(manifest.version, "0.2.0")
        self.assertEqual(manifest.license, "MIT")

    def test_create_plugin_skeleton_file_exists(self):
        output_dir = Path(self.temp_dir) / "output"
        output_dir.mkdir()
        existing_plugin = output_dir / "test_plugin"
        existing_plugin.mkdir()

        with self.assertRaises(FileExistsError):
            create_plugin_skeleton(
                output_dir,
                id="test_plugin",
                name="Test Plugin",
                license="MIT"
            )

        result = create_plugin_skeleton(
            output_dir,
            id="test_plugin",
            name="Test Plugin",
            license="MIT",
            force=True
        )
        self.assertTrue(result.exists())


class PluginStaticRoutesTestCase(ApiDBTestCase):
    def test_add_static_routes_with_frontend_enabled(self):
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
            "frontend_project_enabled": True,
            "frontend_studio_enabled": False
        }
        manifest = PluginManifest(manifest_data)
        routes = []

        add_static_routes(manifest, routes)

        self.assertEqual(len(routes), 2)
        route_paths = [r[0] for r in routes]
        self.assertIn("/frontend/<path:filename>", route_paths)
        self.assertIn("/frontend", route_paths)
        for route_path, resource_class in routes:
            if route_path == "/frontend/<path:filename>":
                instance = resource_class()
                self.assertEqual(instance.plugin_id, "test_plugin")

    def test_add_static_routes_without_frontend(self):
        """Test adding static routes when frontend is disabled"""
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
            "frontend_project_enabled": False,
            "frontend_studio_enabled": False
        }
        manifest = PluginManifest(manifest_data)
        routes = []

        add_static_routes(manifest, routes)

        self.assertEqual(len(routes), 0)

