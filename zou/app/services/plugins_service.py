import zipfile
import semver
import shutil
from pathlib import Path

from zou.app import config, db
from zou.app.models.plugin import Plugin
from zou.app.utils.plugins import PluginManifest


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
        already_installed = False
        if plugin:
            current = semver.Version.parse(plugin.version)
            new = semver.Version.parse(str(manifest.version))
            if not force and new <= current:
                raise ValueError(
                    f"Plugin version {new} is not newer than {current}."
                )
            plugin.update_no_commit(manifest.to_model_dict())
            already_installed = True
        else:
            plugin = Plugin.create_no_commit(**manifest.to_model_dict())

        install_plugin_files(manifest.id, path, already_installed)
    except Exception:
        uninstall_plugin_files(manifest.id)
        db.session.rollback()
        db.session.remove()
        raise

    Plugin.commit()
    return plugin.serialize()


def install_plugin_files(plugin_id, path, already_installed=False):
    """
    Install plugin files.
    """
    path = Path(path)
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id
    if already_installed and plugin_path.exists():
        shutil.rmtree(plugin_path)

    plugin_path.mkdir(parents=True, exist_ok=True)

    if path.is_dir():
        shutil.copytree(path, plugin_path, dirs_exist_ok=True)
    elif zipfile.is_zipfile(path):
        shutil.unpack_archive(path, plugin_path, format="zip")
    else:
        raise ValueError(
            f"Plugin path '{path}' is not a valid zip file or a directory."
        )

    return plugin_path


def uninstall_plugin_files(plugin_id):
    """
    Uninstall plugin files.
    """
    plugin_path = Path(config.PLUGIN_FOLDER) / plugin_id
    if plugin_path.exists():
        shutil.rmtree(plugin_path)
        return True
    return False


def uninstall_plugin(plugin_id):
    """
    Uninstall a plugin.
    """
    installed = uninstall_plugin_files(plugin_id)
    plugin = Plugin.query.filter_by(plugin_id=plugin_id).one_or_none()
    if plugin is not None:
        installed = True
        plugin.delete()

    if not installed:
        raise ValueError(f"Plugin '{plugin_id}' is not installed.")
    return True


def create_plugin_skeleton(
    path,
    id,
    name,
    description=None,
    version=None,
    maintainer=None,
    website=None,
    license=None,
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

    manifest.validate()
    manifest.write_to_path(plugin_path)

    return plugin_path


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
