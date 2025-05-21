import semver
from pathlib import Path

from zou.app import config, db
from zou.app.models.plugin import Plugin
from zou.app.utils.plugins import (
    PluginManifest,
    run_plugin_migrations,
    downgrade_plugin_migrations,
    uninstall_plugin_files,
    install_plugin_files,
)


def install_plugin(path, force=False):
    """
    Install a plugin.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Plugin path '{path}' does not exist.")

    manifest = PluginManifest.from_plugin_path(path)
    plugin = Plugin.query.filter_by(plugin_id=manifest.id).one_or_none()

    try:
        if plugin:
            current = semver.Version.parse(plugin.version)
            new = semver.Version.parse(str(manifest.version))
            if not force and new <= current:
                raise ValueError(
                    f"Plugin version {new} is not newer than {current}."
                )
            plugin.update_no_commit(manifest.to_model_dict())
        else:
            plugin = Plugin.create_no_commit(**manifest.to_model_dict())

        plugin_path = install_plugin_files(
            path, Path(config.PLUGIN_FOLDER) / manifest.id
        )
        run_plugin_migrations(plugin_path, plugin)
    except Exception:
        uninstall_plugin_files(manifest.id)
        db.session.rollback()
        db.session.remove()
        raise

    Plugin.commit()
    return plugin.serialize()


def uninstall_plugin(plugin_id):
    """
    Uninstall a plugin.
    """
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id
    downgrade_plugin_migrations(plugin_path)
    installed = uninstall_plugin_files(plugin_path)
    plugin = Plugin.query.filter_by(plugin_id=plugin_id).one_or_none()
    if plugin is not None:
        installed = True
        plugin.delete()

    if not installed:
        raise ValueError(f"Plugin '{plugin_id}' is not installed.")
    return True
