import email.utils
import spdx_license_list
import zipfile
import importlib
import importlib.util
import sys
import os
import tomlkit
import traceback
import semver
import shutil
import subprocess
import tempfile

from alembic import command
from alembic.config import Config
from collections.abc import MutableMapping
from flask import Blueprint, current_app
from flask_restful import Resource
from pathlib import Path

from zou.app.utils.api import configure_api_from_blueprint

from flask import send_from_directory, abort, current_app


class StaticResource(Resource):

    plugin_id = None

    def get(self, filename="index.html"):

        print(self.plugin_id)
        static_folder = (
            Path(current_app.config.get("PLUGIN_FOLDER", "plugins"))
            / self.plugin_id
            / "frontend"
            / "dist"
        )

        if filename == "":
            filename = "index.html"

        file_path = static_folder / filename
        if not file_path.exists() or not file_path.is_file():
            abort(404)

        if filename == "":
            filename = "index.html"

        return send_from_directory(
            str(static_folder), filename, conditional=True, max_age=0
        )


class PluginManifest(MutableMapping):
    def __init__(self, data):
        super().__setattr__("data", data)
        self.validate()

    @classmethod
    def from_plugin_path(cls, path):
        path = Path(path)
        if path.is_dir():
            return cls.from_file(path / "manifest.toml")
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                with z.open("manifest.toml") as f:
                    data = tomlkit.load(f)
            return cls(data)
        else:
            raise ValueError(f"Invalid plugin path: {path}")

    @classmethod
    def from_file(cls, path):
        with open(path, "rb") as f:
            data = tomlkit.load(f)
        return cls(data)

    def write_to_path(self, path):
        path = Path(path)
        with open(path / "manifest.toml", "w", encoding="utf-8") as f:
            tomlkit.dump(self.data, f)

    def validate(self):
        semver.Version.parse(str(self.data["version"]))
        spdx_license_list.LICENSES[self.data["license"]]
        if "maintainer" in self.data:
            name, email_addr = email.utils.parseaddr(self.data["maintainer"])
            self.data["maintainer_name"] = name
            self.data["maintainer_email"] = email_addr

        if "frontend_project_enabled" not in self.data:
            self.data["frontend_project_enabled"] = False
        if "frontend_studio_enabled" not in self.data:
            self.data["frontend_studio_enabled"] = False

    def to_model_dict(self):
        return {
            "plugin_id": self.data["id"],
            "name": self.data["name"],
            "description": self.data.get("description"),
            "version": str(self.data["version"]),
            "maintainer_name": self.data.get("maintainer_name"),
            "maintainer_email": self.data.get("maintainer_email"),
            "website": self.data.get("website"),
            "license": self.data["license"],
            "frontend_project_enabled": self.data.get(
                "frontend_project_enabled", False
            ),
            "frontend_studio_enabled": self.data.get(
                "frontend_studio_enabled", False
            ),
            "icon": self.data.get("icon", ""),
        }

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return f"<PluginManifest {self.data!r}>"

    def __getattr__(self, attr):
        try:
            return self.data[attr]
        except KeyError:
            raise AttributeError(f"'PluginManifest' has no attribute '{attr}'")

    def __setattr__(self, attr, value):
        if attr == "data":
            super().__setattr__(attr, value)
        else:
            self.data[attr] = value


def load_plugin(app, plugin_path, init_plugin=True):
    """
    Load a plugin from the plugin folder.
    """
    plugin_path = Path(plugin_path)
    manifest = PluginManifest.from_plugin_path(plugin_path)
    plugin_module = importlib.import_module(manifest["id"])

    if not hasattr(plugin_module, "routes"):
        raise Exception(f"Plugin {manifest['id']} has no routes.")

    routes = plugin_module.routes
    add_static_routes(manifest, routes)
    blueprint = Blueprint(manifest["id"], manifest["id"])
    configure_api_from_blueprint(blueprint, routes)
    app.register_blueprint(blueprint, url_prefix=f"/plugins/{manifest['id']}")

    return plugin_module


def load_plugins(app):
    """
    Load plugins from the plugin folder.
    """
    plugin_folder = Path(app.config["PLUGIN_FOLDER"])
    if plugin_folder.exists():
        abs_plugin_path = str(plugin_folder.absolute())
        if abs_plugin_path not in sys.path:
            sys.path.insert(0, abs_plugin_path)

        for plugin_id in os.listdir(plugin_folder):
            try:
                load_plugin(app, plugin_folder / plugin_id)
                app.logger.info(f"Plugin {plugin_id} loaded.")
            except ImportError as e:
                app.logger.error(f"Plugin {plugin_id} failed to import: {e}")
            except Exception as e:
                app.logger.error(
                    f"Plugin {plugin_id} failed to initialize: {e}"
                )
                app.logger.debug(traceback.format_exc())

        if abs_plugin_path in sys.path:
            sys.path.remove(abs_plugin_path)


def migrate_plugin_db(plugin_path, message):
    """
    Generates Alembic migration files in path/migrations.
    """
    plugin_path = Path(plugin_path).absolute()
    models_path = plugin_path / "models.py"

    if not models_path.exists():
        raise FileNotFoundError(f"'models.py' not found in '{plugin_path}'")

    manifest = PluginManifest.from_plugin_path(plugin_path)

    module_name = f"_plugin_models_{manifest['id']}"
    spec = importlib.util.spec_from_file_location(module_name, models_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load 'models.py' from '{plugin_path}'")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        migrations_dir = plugin_path / "migrations"
        versions_dir = migrations_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)

        alembic_cfg = Config()
        alembic_cfg.config_file_name = str(
            plugin_path / "migrations" / "alembic.ini"
        )
        alembic_cfg.set_main_option("script_location", str(migrations_dir))
        alembic_cfg.set_main_option(
            "sqlalchemy.url", current_app.config["SQLALCHEMY_DATABASE_URI"]
        )

        command.revision(alembic_cfg, autogenerate=True, message=message)
    finally:
        del sys.modules[module_name]


def run_plugin_migrations(plugin_path, plugin):
    """
    Run plugin migrations.
    """
    plugin_path = Path(plugin_path)

    alembic_cfg = Config()
    alembic_cfg.config_file_name = str(
        plugin_path / "migrations" / "alembic.ini"
    )
    alembic_cfg.set_main_option(
        "script_location", str(plugin_path / "migrations")
    )
    alembic_cfg.set_main_option(
        "sqlalchemy.url", current_app.config["SQLALCHEMY_DATABASE_URI"]
    )

    command.upgrade(alembic_cfg, "head")

    script = command.ScriptDirectory.from_config(alembic_cfg)
    head_revision = script.get_current_head()

    plugin.revision = head_revision

    return head_revision


def downgrade_plugin_migrations(plugin_path):
    """
    Downgrade plugin migrations to base.
    """
    plugin_path = Path(plugin_path)
    manifest = PluginManifest.from_plugin_path(plugin_path)

    alembic_cfg = Config()
    alembic_cfg.config_file_name = str(
        plugin_path / "migrations" / "alembic.ini"
    )
    alembic_cfg.set_main_option(
        "script_location", str(plugin_path / "migrations")
    )
    alembic_cfg.set_main_option(
        "sqlalchemy.url", current_app.config["SQLALCHEMY_DATABASE_URI"]
    )

    try:
        command.downgrade(alembic_cfg, "base")
    except Exception as e:
        current_app.logger.warning(
            f"Downgrade failed for plugin {manifest.id}: {e}"
        )


def create_plugin_package(path, output_path, force=False):
    """
    Create a plugin package.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Plugin path '{path}' does not exist.")

    manifest = PluginManifest.from_plugin_path(path)

    output_path = Path(output_path)
    if not output_path.suffix == ".zip":
        output_path /= f"{manifest.id}-{manifest.version}.zip"
    if output_path.exists():
        if force:
            output_path.unlink()
        else:
            raise FileExistsError(
                f"Output path '{output_path}' already exists."
            )

    output_path = shutil.make_archive(
        output_path.with_suffix(""),
        "zip",
        path,
    )
    return output_path


def create_plugin_skeleton(
    path,
    id,
    name,
    description=None,
    version=None,
    maintainer=None,
    website=None,
    license=None,
    icon=None,
    force=False,
):
    plugin_template_path = (
        Path(__file__).parent.parent.parent / "plugin_template"
    )
    plugin_path = Path(path) / id

    if plugin_path.exists():
        if force:
            shutil.rmtree(plugin_path)
        else:
            raise FileExistsError(
                f"Plugin '{id}' already exists in {plugin_path}."
            )

    shutil.copytree(plugin_template_path, plugin_path)

    manifest = PluginManifest.from_file(plugin_path / "manifest.toml")

    manifest.id = id
    manifest.name = name
    if description:
        manifest.description = description
    if version:
        manifest.version = version
    if maintainer:
        manifest.maintainer = maintainer
    if website:
        manifest.website = website
    if license:
        manifest.license = license
    if icon:
        manifest.icon = icon
    manifest.validate()
    manifest.write_to_path(plugin_path)

    return plugin_path


def install_plugin_files(files_path, installation_path):
    """
    Install plugin files.
    """
    files_path = Path(files_path)
    installation_path = Path(installation_path)

    installation_path.mkdir(parents=True, exist_ok=True)

    if files_path.is_dir():
        shutil.copytree(files_path, installation_path, dirs_exist_ok=True)
    elif zipfile.is_zipfile(files_path):
        shutil.unpack_archive(files_path, installation_path, format="zip")
    else:
        raise ValueError(
            f"Plugin path '{files_path}' is not a valid zip file or a directory."
        )

    return installation_path


def uninstall_plugin_files(plugin_path):
    """
    Uninstall plugin files.
    """
    plugin_path = Path(plugin_path)
    if plugin_path.exists():
        shutil.rmtree(plugin_path)
        return True
    return False


def clone_git_repo(git_url, temp_dir=None):
    """
    Clone a git repository to a temporary directory.
    Returns the path to the cloned directory.
    """
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp(prefix="zou_plugin_")

    temp_dir = Path(temp_dir)
    repo_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = temp_dir / repo_name

    print(f"[Plugins] Cloning {git_url}...")

    try:
        subprocess.run(
            ["git", "clone", git_url, str(clone_path)],
            check=True,
            capture_output=True,
            timeout=300,
        )
        print(f"[Plugins] Successfully cloned {git_url}")
        return clone_path
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        raise ValueError(f"Failed to clone repository {git_url}: {error_msg}")
    except FileNotFoundError:
        raise ValueError(
            "git is not available. Please install git to clone repositories."
        )


def add_static_routes(manifest, routes):
    """
    Add static routes to the manifest.
    """

    class PluginStaticResource(StaticResource):

        def __init__(self):
            self.plugin_id = manifest.id
            super().__init__()

    if (
        manifest["frontend_project_enabled"]
        or manifest["frontend_studio_enabled"]
    ):
        routes.append((f"/frontend/<path:filename>", PluginStaticResource))
        routes.append((f"/frontend", PluginStaticResource))
