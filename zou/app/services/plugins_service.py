import importlib
import logging
import shutil
import sys
from pathlib import Path

import semver

from zou.app import config
from zou.app.models.plugin import Plugin
from zou.app.utils.plugins import (
    PluginManifest,
    clone_git_repo,
    downgrade_plugin_migrations,
    download_zip_url,
    install_plugin_files,
    run_plugin_migrations,
    uninstall_plugin_files,
)

logger = logging.getLogger(__name__)


def install_plugin(path, force=False):
    """
    Install a plugin. The source can be a local path, a zip file or a git
    repository URL. The steps are:
    - Call the pre_install hook.
    - Create the plugin folder and copy the files into it.
    - Run the migrations.
    - Call the post_install hook.
    """
    is_zip_url = path.startswith(("http://", "https://")) and path.endswith(
        ".zip"
    )
    is_git_url = not is_zip_url and path.startswith(
        ("http://", "https://", "git://", "ssh://", "git@")
    )

    temp_dir = None
    try:
        if is_zip_url:
            zip_path = download_zip_url(path)
            temp_dir = zip_path.parent
            path = zip_path
        elif is_git_url:
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
            logger.info(
                f"[Plugins] Upgrading {manifest.id}"
                f" from {current} to {new}..."
            )
            if not force and new <= current:
                logger.warning(
                    f"⚠️  [Plugins] Version {new} is not newer"
                    f" than {current}."
                )
            plugin.update(manifest.to_model_dict())
            logger.info(f"[Plugins] Plugin {manifest.id} upgraded.")
        else:
            logger.info(f"[Plugins] Installing plugin {manifest.id}...")
            plugin = Plugin.create(**manifest.to_model_dict())
            logger.info(f"[Plugins] Plugin {manifest.id} installed.")

        logger.info(
            f"[Plugins] Running database migrations for {manifest.id}..."
        )
        plugin_path = install_plugin_files(
            path, Path(config.PLUGIN_FOLDER) / manifest.id
        )
        run_plugin_migrations(plugin_path, plugin)
        logger.info(
            f"[Plugins] Database migrations for {manifest.id} applied."
        )

        # Get the plugin instance again after the migrations. The Alembic
        # operations can detach it from the session.
        plugin = Plugin.get_by(plugin_id=manifest.id)

        _run_plugin_hook(manifest.id, plugin_path, "post_install", manifest)

        print_added_routes(plugin.plugin_id, plugin_path)
        return plugin.serialize()
    except Exception:
        logger.warning(
            "❌ [Plugins] An error occurred while installing/updating plugin"
        )
        raise
    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir)


def uninstall_plugin(plugin_id):
    """
    Uninstall a plugin. The steps are:
    - Call the pre_uninstall hook.
    - Downgrade the migrations.
    - Call the post_uninstall hook.
    - Remove the files and the folder, and delete the database entry.
    If the plugin has no files and no database entry, or if its files have
    no readable manifest, raise ValueError.
    """
    logger.info(f"[Plugins] Uninstalling plugin {plugin_id}...")
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id

    # A plugin without files (only a database entry) stays uninstallable.
    # If the files exist, the downgrade needs the manifest to find the
    # version table of the plugin: without it, the plugin tables would stay
    # and a new install would fail.
    manifest = None
    if plugin_path.exists():
        try:
            manifest = PluginManifest.from_plugin_path(plugin_path)
        except Exception as e:
            raise ValueError(
                f"Plugin '{plugin_id}' has no readable manifest, its "
                f"migrations cannot be downgraded: {e}"
            ) from e

    _run_plugin_hook(plugin_id, plugin_path, "pre_uninstall", manifest)

    if manifest is not None:
        downgrade_plugin_migrations(plugin_path)

    # Run post_uninstall before the file removal: the module must still exist.
    _run_plugin_hook(plugin_id, plugin_path, "post_uninstall", manifest)

    installed = uninstall_plugin_files(plugin_path)
    plugin = Plugin.query.filter_by(plugin_id=plugin_id).one_or_none()
    if plugin is not None:
        installed = True
        plugin.delete()

    if not installed:
        raise ValueError(f"Plugin '{plugin_id}' is not installed.")

    logger.info(f"[Plugins] Plugin {plugin_id} uninstalled.")
    return True


def _import_plugin_module(plugin_id, plugin_path):
    """
    Import a plugin module dynamically from its install path. Return the
    module, or None if the import fails.
    """
    plugin_path = Path(plugin_path)
    plugin_folder = plugin_path.parent
    abs_plugin_path = str(plugin_folder.absolute())
    added_to_path = abs_plugin_path not in sys.path

    if added_to_path:
        sys.path.insert(0, abs_plugin_path)

    try:
        if plugin_id in sys.modules:
            return sys.modules[plugin_id]
        return importlib.import_module(plugin_id)
    except ImportError as e:
        logger.warning(f"⚠️  [Plugins] Could not import plugin module: {e}")
        return None
    except Exception:
        # The import can fail on a reinstall (for example, the SQLAlchemy
        # table is already defined). If the partially loaded module exists,
        # return it.
        if plugin_id in sys.modules:
            return sys.modules[plugin_id]
        return None
    finally:
        if added_to_path and abs_plugin_path in sys.path:
            sys.path.remove(abs_plugin_path)


def _run_plugin_hook(plugin_id, plugin_path, hook_name, *args):
    """
    Run a lifecycle hook (pre_install, post_install, pre_uninstall,
    post_uninstall) on a plugin module, if the hook exists. Log the errors.
    An error never stops the install or the uninstall.
    """
    try:
        plugin_module = _import_plugin_module(plugin_id, plugin_path)
        if plugin_module is None:
            return

        hook = getattr(plugin_module, hook_name, None)
        if hook is not None:
            logger.info(f"[Plugins] Running {hook_name} for {plugin_id}...")
            hook(*args)
            logger.info(f"[Plugins] {hook_name} for {plugin_id} completed.")
    except Exception as e:
        logger.warning(
            f"⚠️  [Plugins] {hook_name} failed for {plugin_id}: {e}"
        )


def print_added_routes(plugin_id, plugin_path):
    """
    Log the routes that the given plugin adds.
    """
    logger.info(f"[Plugins] Routes added by {plugin_id}:")

    plugin_module = _import_plugin_module(plugin_id, plugin_path)
    if plugin_module is not None and hasattr(plugin_module, "routes"):
        for route in plugin_module.routes:
            logger.info(f"  - /api/plugins/{plugin_id}{route[0]}")
    else:
        logger.info("  (No routes variable found in plugin)")

    logger.info("--------------------------------")


def get_plugins():
    """
    Return all the plugins.
    """
    return [plugin.present() for plugin in Plugin.query.all()]
