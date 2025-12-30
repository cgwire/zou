import semver
import shutil
from pathlib import Path

from zou.app import config, db
from zou.app.models.plugin import Plugin
from zou.app.utils.plugins import (
    PluginManifest,
    run_plugin_migrations,
    downgrade_plugin_migrations,
    uninstall_plugin_files,
    install_plugin_files,
    clone_git_repo,
)


def install_plugin(path, force=False):
    """
    Install a plugin: create folder, copy files, run migrations.
    Supports local paths, zip files, and git repository URLs.
    """
    is_git_url = (
        path.startswith("http://")
        or path.startswith("https://")
        or path.startswith("git://")
        or path.startswith("ssh://")
        or path.startswith("git@")
    )

    temp_dir = None
    if is_git_url:
        cloned_path = clone_git_repo(path)
        temp_dir = cloned_path.parent
        path = cloned_path
    else:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Plugin path '{path}' does not exist.")

    manifest = PluginManifest.from_plugin_path(path)
    plugin = Plugin.query.filter_by(plugin_id=manifest.id).one_or_none()

    try:
        if plugin:
            current = semver.Version.parse(plugin.version)
            new = semver.Version.parse(str(manifest.version))
            print(
                f"[Plugins] Upgrading plugin {manifest.id} from version {current} to {new}..."
            )
            if not force and new <= current:
                print(f"⚠️  Plugin version {new} is not newer than {current}.")
            plugin.update_no_commit(manifest.to_model_dict())
            print(f"[Plugins] Plugin {manifest.id} upgraded.")
        else:
            print(f"[Plugins] Installing plugin {manifest.id}...")
            plugin = Plugin.create_no_commit(**manifest.to_model_dict())
            print(f"[Plugins] Plugin {manifest.id} installed.")

        print(f"[Plugins] Running database migrations for {manifest.id}...")
        plugin_path = install_plugin_files(
            path, Path(config.PLUGIN_FOLDER) / manifest.id
        )
        run_plugin_migrations(plugin_path, plugin)
        print(f"[Plugins] Database migrations for {manifest.id} applied.")
    except Exception:
        print(
            f"❌ [Plugins] An error occurred while installing/updating {manifest.id}..."
        )
        raise

    Plugin.commit()
    print_added_routes(plugin, plugin_path)

    if is_git_url:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)

    return plugin.serialize()


def uninstall_plugin(plugin_id):
    """
    Uninstall a plugin: downgrade migrations, remove files,
    delete from database and remove folder.
    """
    print(f"[Plugins] Uninstalling plugin {plugin_id}...")
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id
    downgrade_plugin_migrations(plugin_path)
    installed = uninstall_plugin_files(plugin_path)
    plugin = Plugin.query.filter_by(plugin_id=plugin_id).one_or_none()
    if plugin is not None:
        installed = True
        plugin.delete()

    if not installed:
        raise ValueError(f"Plugin '{plugin_id}' is not installed.")

    print(f"[Plugins] Plugin {plugin_id} uninstalled.")
    return True


def print_added_routes(plugin, plugin_path):
    """
    Print the added routes for a plugin.
    """
    import importlib
    import sys

    print(f"[Plugins] Routes added by {plugin.plugin_id}:")
    plugin_path = Path(plugin_path)

    plugin_folder = plugin_path.parent
    abs_plugin_path = str(plugin_folder.absolute())
    if abs_plugin_path not in sys.path:
        sys.path.insert(0, abs_plugin_path)

    try:
        plugin_module = importlib.import_module(plugin.plugin_id)
        if hasattr(plugin_module, "routes"):
            routes = plugin_module.routes
            for route in routes:
                print(f"  - /plugins/{plugin.plugin_id}{route[0]}")
        else:
            print("  (No routes variable found in plugin)")
    except ImportError as e:
        print(f"  ⚠️  Could not import plugin module: {e}")
    finally:
        if abs_plugin_path in sys.path:
            sys.path.remove(abs_plugin_path)

    print("--------------------------------")


def get_plugins():
    """
    Get all plugins.
    """
    return [plugin.present() for plugin in Plugin.query.all()]
