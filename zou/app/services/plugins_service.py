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
    Install a plugin: create folder, copy files, run migrations,
    and call pre/post install hooks.
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
    try:
        if is_git_url:
            cloned_path = clone_git_repo(path)
            temp_dir = cloned_path.parent
            path = cloned_path
        else:
            path = Path(path)
            if not path.exists():
                raise FileNotFoundError(
                    f"Plugin path '{path}' does not exist."
                )

        manifest = PluginManifest.from_plugin_path(path)
        plugin = Plugin.get_by(plugin_id=manifest.id)

        _run_plugin_hook(manifest.id, path, "pre_install", manifest)

        if plugin is not None:
            current = semver.Version.parse(plugin.version)
            new = semver.Version.parse(str(manifest.version))
            print(
                f"[Plugins] Upgrading {manifest.id}"
                f" from {current} to {new}..."
            )
            if not force and new <= current:
                print(
                    f"⚠️  [Plugins] Version {new} is not newer"
                    f" than {current}."
                )
            plugin.update(manifest.to_model_dict())
            print(f"[Plugins] Plugin {manifest.id} upgraded.")
        else:
            print(f"[Plugins] Installing plugin {manifest.id}...")
            plugin = Plugin.create(**manifest.to_model_dict())
            print(f"[Plugins] Plugin {manifest.id} installed.")

        print(
            f"[Plugins] Running database migrations"
            f" for {manifest.id}..."
        )
        plugin_path = install_plugin_files(
            path, Path(config.PLUGIN_FOLDER) / manifest.id
        )
        run_plugin_migrations(plugin_path, plugin)
        print(
            f"[Plugins] Database migrations for {manifest.id} applied."
        )

        # Re-query plugin instance after migrations
        # (Alembic operations may have detached it from the session)
        plugin = Plugin.get_by(plugin_id=manifest.id)

        _run_plugin_hook(
            manifest.id, plugin_path, "post_install", manifest
        )

        print_added_routes(plugin.plugin_id, plugin_path)
        return plugin.serialize()
    except Exception:
        print(
            f"❌ [Plugins] An error occurred while"
            f" installing/updating plugin..."
        )
        raise
    finally:
        if is_git_url and temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)


def uninstall_plugin(plugin_id):
    """
    Uninstall a plugin: call pre/post uninstall hooks, downgrade
    migrations, remove files, delete from database and remove folder.
    """
    print(f"[Plugins] Uninstalling plugin {plugin_id}...")
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id

    manifest = None
    try:
        manifest = PluginManifest.from_plugin_path(plugin_path)
    except Exception:
        pass

    _run_plugin_hook(plugin_id, plugin_path, "pre_uninstall", manifest)

    downgrade_plugin_migrations(plugin_path)

    # Run post_uninstall before removing files (module must still exist)
    _run_plugin_hook(plugin_id, plugin_path, "post_uninstall", manifest)

    installed = uninstall_plugin_files(plugin_path)
    plugin = Plugin.query.filter_by(plugin_id=plugin_id).one_or_none()
    if plugin is not None:
        installed = True
        plugin.delete()

    if not installed:
        raise ValueError(f"Plugin '{plugin_id}' is not installed.")

    print(f"[Plugins] Plugin {plugin_id} uninstalled.")
    return True


def _import_plugin_module(plugin_id, plugin_path):
    """
    Import a plugin module dynamically from its install path.
    Returns the module or None if import fails.
    """
    import importlib
    import sys

    plugin_path = Path(plugin_path)
    plugin_folder = plugin_path.parent
    abs_plugin_path = str(plugin_folder.absolute())
    added_to_path = abs_plugin_path not in sys.path

    if added_to_path:
        sys.path.insert(0, abs_plugin_path)

    try:
        if plugin_id in sys.modules:
            return importlib.reload(sys.modules[plugin_id])
        return importlib.import_module(plugin_id)
    except ImportError as e:
        print(f"⚠️  [Plugins] Could not import plugin module: {e}")
        return None
    finally:
        if added_to_path and abs_plugin_path in sys.path:
            sys.path.remove(abs_plugin_path)


def _run_plugin_hook(plugin_id, plugin_path, hook_name, *args):
    """
    Run a lifecycle hook (pre_install, post_install, pre_uninstall,
    post_uninstall) on a plugin module if it exists.
    """
    plugin_module = _import_plugin_module(plugin_id, plugin_path)
    if plugin_module is None:
        return

    hook = getattr(plugin_module, hook_name, None)
    if hook is not None:
        print(f"[Plugins] Running {hook_name} for {plugin_id}...")
        hook(*args)
        print(f"[Plugins] {hook_name} for {plugin_id} completed.")


def print_added_routes(plugin_id, plugin_path):
    """
    Print the added routes for a plugin.
    """
    print(f"[Plugins] Routes added by {plugin_id}:")

    plugin_module = _import_plugin_module(plugin_id, plugin_path)
    if plugin_module is not None and hasattr(plugin_module, "routes"):
        for route in plugin_module.routes:
            print(f"  - /plugins/{plugin_id}{route[0]}")
    else:
        print("  (No routes variable found in plugin)")

    print("--------------------------------")


def get_plugins():
    """
    Get all plugins.
    """
    return [plugin.present() for plugin in Plugin.query.all()]
