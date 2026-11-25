# -*- coding: UTF-8 -*-
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Blueprint, Flask
from werkzeug.exceptions import NotFound

from zou.app.utils.api import configure_api_from_blueprint
from zou.app.utils.plugins import (
    PluginManifest,
    StaticResource,
    _build_plugin_alembic_config,
    add_static_routes,
    clone_git_repo,
    create_plugin_package,
    create_plugin_skeleton,
    download_zip_url,
    install_plugin_files,
    load_plugin,
    load_plugins,
    migrate_plugin_db,
    uninstall_plugin_files,
)


class PluginManifestTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_plugin_manifest_from_file(self):
        manifest_path = Path(self.temp_dir) / "manifest.toml"
        manifest_content = """id = "test_plugin"
name = "Test Plugin"
description = "A test plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
website = "https://example.com"
license = "MIT"
frontend_project_enabled = false
frontend_studio_enabled = false
"""
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
        manifest_content = """id = "test_plugin"
name = "Test Plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
license = "MIT"
"""
        manifest_path.write_text(manifest_content)

        manifest = PluginManifest.from_plugin_path(plugin_dir)

        self.assertEqual(manifest["id"], "test_plugin")
        self.assertEqual(manifest["name"], "Test Plugin")

    def test_plugin_manifest_from_plugin_path_invalid(self):
        invalid_path = Path(self.temp_dir) / "invalid.txt"
        invalid_path.write_text("not a plugin")

        with self.assertRaises(ValueError) as context:
            PluginManifest.from_plugin_path(invalid_path)

        self.assertIn("Invalid plugin path", str(context.exception))

    def test_plugin_manifest_validate_version(self):
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "invalid-version",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
        }

        with self.assertRaises(ValueError):
            PluginManifest(manifest_data)

    def test_plugin_manifest_validate_license(self):
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "INVALID-LICENSE",
        }

        with self.assertRaises(KeyError):
            PluginManifest(manifest_data)

    def test_plugin_manifest_validate_maintainer(self):
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
        }

        manifest = PluginManifest(manifest_data)

        self.assertEqual(manifest.data.get("maintainer_name"), "Test Author")
        self.assertEqual(
            manifest.data.get("maintainer_email"), "test@example.com"
        )

    def test_plugin_manifest_to_model_dict(self):
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
            "icon": "test-icon",
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
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
        }

        manifest = PluginManifest(manifest_data)
        output_path = Path(self.temp_dir) / "output"
        output_path.mkdir()

        manifest.write_to_path(output_path)

        written_manifest = PluginManifest.from_file(
            output_path / "manifest.toml"
        )
        self.assertEqual(written_manifest["id"], "test_plugin")
        self.assertEqual(written_manifest["name"], "Test Plugin")


class PluginFilesTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
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
        with zipfile.ZipFile(zip_path, "w") as zf:
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

        self.assertIn(
            "not a valid zip file or a directory", str(context.exception)
        )

    def test_uninstall_plugin_files(self):
        plugin_path = Path(self.temp_dir) / "plugin"
        plugin_path.mkdir()
        (plugin_path / "file1.txt").write_text("content1")
        result = uninstall_plugin_files(plugin_path)
        self.assertTrue(result)
        self.assertFalse(plugin_path.exists())

    def test_uninstall_plugin_files_nonexistent(self):
        nonexistent_path = Path(self.temp_dir) / "nonexistent"
        result = uninstall_plugin_files(nonexistent_path)
        self.assertFalse(result)


class PluginDownloadTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("zou.app.utils.plugins.requests")
    def test_download_zip_url(self, mock_requests):
        zip_content = self._create_test_zip()
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [zip_content]
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        url = "https://github.com/org/repo/releases/download/v0.1.0/plugin.zip"
        result = download_zip_url(url, self.temp_dir)

        self.assertTrue(result.exists())
        self.assertEqual(result.name, "plugin.zip")
        self.assertTrue(zipfile.is_zipfile(result))
        mock_requests.get.assert_called_once_with(
            url, stream=True, timeout=300
        )

    @patch("zou.app.utils.plugins.requests")
    def test_download_zip_url_http_error(self, mock_requests):
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = (
            requests.exceptions.HTTPError("404 Not Found")
        )
        mock_requests.get.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            download_zip_url(
                "https://example.com/nonexistent.zip",
                self.temp_dir,
            )

    def _create_test_zip(self):
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("manifest.toml", 'id = "test"\nversion = "0.1.0"')
            zf.writestr("__init__.py", "routes = []")
        return buffer.getvalue()


class PluginPackageTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_plugin_package(self):
        plugin_dir = Path(self.temp_dir) / "test_plugin"
        plugin_dir.mkdir()
        manifest_path = plugin_dir / "manifest.toml"
        manifest_content = """id = "test_plugin"
name = "Test Plugin"
version = "0.1.0"
maintainer = "Test Author <test@example.com>"
license = "MIT"
"""
        manifest_path.write_text(manifest_content)
        (plugin_dir / "file1.txt").write_text("content1")
        output_path = Path(self.temp_dir) / "output.zip"

        target_path = create_plugin_package(plugin_dir, output_path)
        result = Path(target_path)

        self.assertTrue(result.exists())
        self.assertEqual(result.suffix, ".zip")

        with zipfile.ZipFile(result, "r") as zf:
            files = zf.namelist()
            self.assertIn("manifest.toml", files)
            self.assertIn("file1.txt", files)


class PluginSkeletonTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
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
            icon="test-icon",
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
                output_dir, id="test_plugin", name="Test Plugin", license="MIT"
            )

        result = create_plugin_skeleton(
            output_dir,
            id="test_plugin",
            name="Test Plugin",
            license="MIT",
            force=True,
        )
        self.assertTrue(result.exists())


class PluginStaticRoutesTestCase(unittest.TestCase):
    def test_add_static_routes_with_frontend_enabled(self):
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
            "frontend_project_enabled": True,
            "frontend_studio_enabled": False,
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
        manifest_data = {
            "id": "test_plugin",
            "name": "Test Plugin",
            "version": "0.1.0",
            "maintainer": "Test Author <test@example.com>",
            "license": "MIT",
            "frontend_project_enabled": False,
            "frontend_studio_enabled": False,
        }
        manifest = PluginManifest(manifest_data)
        routes = []

        add_static_routes(manifest, routes)

        self.assertEqual(routes, [])


class PluginLoadTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        sys.path.insert(0, self.temp_dir)

    def tearDown(self):
        sys.path.remove(self.temp_dir)
        sys.modules.pop("frontend_only_plugin", None)
        shutil.rmtree(self.temp_dir)

    def test_load_plugin_without_routes(self):
        plugin_dir = Path(self.temp_dir) / "frontend_only_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("")
        (plugin_dir / "manifest.toml").write_text(
            'id = "frontend_only_plugin"\n'
            'name = "Frontend Only Plugin"\n'
            'version = "0.1.0"\n'
            'license = "MIT"\n'
            "frontend_project_enabled = true\n"
        )
        app = Flask(__name__)

        load_plugin(app, plugin_dir)

        rules = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertIn("/plugins/frontend_only_plugin/frontend", rules)


class PluginAlembicConfigTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_build_config_with_percent_in_db_uri(self):
        from zou.app import app

        uri = "postgresql://user:i4xVGz%2189Dsoi@localhost:5432/zoudb"
        with app.app_context():
            with patch.dict(app.config, {"SQLALCHEMY_DATABASE_URI": uri}):
                alembic_cfg = _build_plugin_alembic_config(self.temp_dir)
        self.assertEqual(alembic_cfg.get_main_option("sqlalchemy.url"), uri)


MINIMAL_MANIFEST = 'version = "0.1.0"\nlicense = "MIT"\n'


def write_plugin(folder, plugin_id, init_code="", extra_manifest=""):
    plugin_dir = Path(folder) / plugin_id
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(init_code)
    (plugin_dir / "manifest.toml").write_text(
        f'id = "{plugin_id}"\nname = "{plugin_id}"\n'
        f"{MINIMAL_MANIFEST}{extra_manifest}"
    )
    return plugin_dir


class PluginManifestAccessTestCase(unittest.TestCase):

    def test_attribute_access(self):
        manifest = PluginManifest(
            {"id": "test_plugin", "version": "0.1.0", "license": "MIT"}
        )

        manifest.name = "Renamed"
        manifest["icon"] = "star"

        self.assertEqual(manifest.data["name"], "Renamed")
        self.assertEqual(manifest.icon, "star")
        self.assertIsNone(getattr(manifest, "website", None))
        with self.assertRaises(AttributeError):
            manifest.website


class StaticResourceTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        plugin_dir = Path(self.temp_dir) / "static_plugin"
        dist = plugin_dir / "frontend" / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("index")
        (dist / "app.js").write_text("app")
        (plugin_dir / "secret.txt").write_text("secret")

        self.app = Flask(__name__)
        self.app.config["PLUGIN_FOLDER"] = self.temp_dir
        manifest = PluginManifest(
            {
                "id": "static_plugin",
                "version": "0.1.0",
                "license": "MIT",
                "frontend_project_enabled": True,
            }
        )
        routes = []
        add_static_routes(manifest, routes)
        blueprint = Blueprint("static_plugin", "static_plugin")
        configure_api_from_blueprint(blueprint, routes)
        self.app.register_blueprint(
            blueprint, url_prefix="/plugins/static_plugin"
        )
        self.client = self.app.test_client()

        self.resource = StaticResource()
        self.resource.plugin_id = "static_plugin"

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_serve_file(self):
        response = self.client.get("/plugins/static_plugin/frontend/app.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"app")

        response = self.client.get("/plugins/static_plugin/frontend")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"index")

    def test_serve_index_for_empty_filename(self):
        with self.app.test_request_context():
            response = self.resource.get("")
            response.direct_passthrough = False
            self.assertEqual(response.data, b"index")

    def test_missing_file_or_directory(self):
        for filename in ["missing.js", "assets"]:
            response = self.client.get(
                f"/plugins/static_plugin/frontend/{filename}"
            )
            self.assertEqual(response.status_code, 404)

    def test_path_outside_dist_is_refused(self):
        with self.app.test_request_context():
            with self.assertRaises(NotFound):
                self.resource.get("../../secret.txt")


class LoadPluginsTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        abs_path = str(Path(self.temp_dir).absolute())
        if abs_path in sys.path:
            sys.path.remove(abs_path)
        for name in [
            "zou_test_good_plugin",
            "zou_test_import_plugin",
            "zou_test_init_plugin",
        ]:
            sys.modules.pop(name, None)
        shutil.rmtree(self.temp_dir)

    def test_failing_plugins_do_not_stop_the_others(self):
        write_plugin(
            self.temp_dir,
            "zou_test_import_plugin",
            init_code="import zou_test_missing_module\n",
        )
        write_plugin(
            self.temp_dir,
            "zou_test_init_plugin",
            init_code='raise RuntimeError("boom")\n',
        )
        write_plugin(
            self.temp_dir,
            "zou_test_good_plugin",
            extra_manifest="frontend_project_enabled = true\n",
        )
        app = Flask(__name__)
        app.config["PLUGIN_FOLDER"] = self.temp_dir

        with self.assertLogs(app.logger, "ERROR") as logs:
            load_plugins(app)

        rules = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertIn("/plugins/zou_test_good_plugin/frontend", rules)
        self.assertIn(str(Path(self.temp_dir).absolute()), sys.path)
        output = "\n".join(logs.output)
        self.assertIn("zou_test_import_plugin failed to import", output)
        self.assertIn("zou_test_init_plugin failed to initialize", output)


class MigratePluginDbTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = write_plugin(self.temp_dir, "zou_test_migrate")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_missing_models_file(self):
        with self.assertRaises(FileNotFoundError):
            migrate_plugin_db(self.plugin_dir, "init")

    @patch("zou.app.utils.plugins.command")
    def test_generate_revision(self, mock_command):
        from zou.app import app

        (self.plugin_dir / "models.py").write_text("LOADED = True\n")
        module_name = "_plugin_models_zou_test_migrate"
        loaded_at_revision = []
        mock_command.revision.side_effect = lambda *args, **kwargs: (
            loaded_at_revision.append(module_name in sys.modules)
        )

        with app.app_context():
            migrate_plugin_db(self.plugin_dir, "init")

        alembic_cfg = mock_command.revision.call_args.args[0]
        self.assertEqual(
            alembic_cfg.get_main_option("version_locations"),
            str(self.plugin_dir.absolute() / "migrations" / "versions"),
        )
        self.assertEqual(
            mock_command.revision.call_args.kwargs,
            {"autogenerate": True, "message": "init"},
        )
        self.assertEqual(loaded_at_revision, [True])
        self.assertNotIn(module_name, sys.modules)


class PluginPackageErrorsTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.plugin_dir = write_plugin(self.temp_dir, "package_plugin")
        self.output_dir = Path(self.temp_dir) / "output"
        self.output_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_missing_plugin_path(self):
        with self.assertRaises(FileNotFoundError):
            create_plugin_package(
                Path(self.temp_dir) / "missing", self.output_dir
            )

    def test_output_directory_and_existing_archive(self):
        archive = Path(create_plugin_package(self.plugin_dir, self.output_dir))
        self.assertEqual(archive, self.output_dir / "package_plugin-0.1.0.zip")

        with self.assertRaises(FileExistsError):
            create_plugin_package(self.plugin_dir, self.output_dir)

        archive.write_text("stale")
        create_plugin_package(self.plugin_dir, self.output_dir, force=True)
        self.assertTrue(zipfile.is_zipfile(archive))


class CloneGitRepoTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("zou.app.utils.plugins.subprocess.run")
    def test_clone(self, mock_run):
        url = "https://github.com/org/my-plugin.git"

        result = clone_git_repo(url, self.temp_dir)

        self.assertEqual(result, Path(self.temp_dir) / "my-plugin")
        self.assertEqual(
            mock_run.call_args.args[0], ["git", "clone", url, str(result)]
        )

    @patch("zou.app.utils.plugins.subprocess.run")
    def test_clone_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr=b"fatal: repository not found"
        )

        with self.assertRaises(ValueError) as context:
            clone_git_repo("https://github.com/org/missing", self.temp_dir)
        self.assertIn("fatal: repository not found", str(context.exception))

    @patch("zou.app.utils.plugins.subprocess.run")
    def test_git_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        with self.assertRaises(ValueError) as context:
            clone_git_repo("https://github.com/org/repo", self.temp_dir)
        self.assertIn("git is not available", str(context.exception))
