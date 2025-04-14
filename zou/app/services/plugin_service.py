import zipfile
import semver
import spdx_license_list
import shutil
import email.utils
import tomlkit

from pathlib import Path

from zou.app import config, db
from zou.app.models.plugin import Plugin


def install_plugin(path, force=False):
    """
    Install a plugin.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Plugin path '{path}' does not exist.")

    try:
        manifest_file = None
        if path.is_dir():
            manifest_file = open(path.joinpath("manifest.toml"), "rb")
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zip_file:
                manifest_file = zip_file.open("manifest.toml", "rb")
        else:
            raise ValueError(
                f"Plugin path '{path}' is not a valid zip file or a directory."
            )

        # Read the plugin metadatas
        manifest = tomlkit.load(manifest_file)
    finally:
        if manifest_file is not None:
            manifest_file.close()

    version = str(semver.Version.parse(manifest["version"]))
    spdx_license_list.LICENSES[manifest["license"]]
    if manifest.get("maintainer") is not None:
        manifest["maintainer_name"], manifest["maintainer_email"] = (
            email.utils.parseaddr(manifest["maintainer"])
        )

    new_plugin_info = {
        "plugin_id": manifest["id"],
        "name": manifest["name"],
        "description": manifest.get("description"),
        "version": version,
        "maintainer_name": manifest["maintainer_name"],
        "maintainer_email": manifest.get("maintainer_email"),
        "website": manifest.get("website"),
        "license": manifest["license"],
    }

    # Check if the plugin is already installed
    plugin = Plugin.query.filter_by(
        plugin_id=new_plugin_info["plugin_id"]
    ).one_or_none()

    already_installed = False
    try:
        if plugin is not None:
            existing_plugin_version = semver.Version.parse(plugin.version)

            if not force:
                if existing_plugin_version == version:
                    raise ValueError(
                        f"Plugin '{manifest['name']}' version {version} is already installed."
                    )
                elif existing_plugin_version > version:
                    raise ValueError(
                        f"Plugin '{manifest['name']}' version {version} is older than the installed version {existing_plugin_version}."
                    )
            already_installed = True
            plugin.update_no_commit(new_plugin_info)
        else:
            plugin = Plugin.create_no_commit(**new_plugin_info)

        install_plugin_files(
            new_plugin_info["plugin_id"],
            path,
            already_installed=already_installed,
        )
    except:
        db.session.rollback()
        db.session.remove()
        raise
    Plugin.commit()

    return plugin.serialize()


def install_plugin_files(plugin_id, path, already_installed=False):
    """
    Install the plugin files.
    """
    path = Path(path)
    plugin_path = Path(config.PLUGIN_FOLDER).joinpath(plugin_id)
    if already_installed:
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
    Uninstall the plugin files.
    """
    plugin_path = Path(config.PLUGIN_FOLDER).joinpath(plugin_id)
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
    """
    Create a plugin skeleton.
    """
    plugin_template_path = Path(__file__).parent.parent.parent.joinpath(
        "plugin_template"
    )
    plugin_path = Path(path).joinpath(id)
    if plugin_path.exists():
        if force:
            shutil.rmtree(plugin_path)
        else:
            raise ValueError(f"Plugin '{id}' already exists in {plugin_path}.")

    shutil.copytree(plugin_template_path, plugin_path)

    manifest_path = plugin_path.joinpath("manifest.toml")
    with open(manifest_path, "r") as manifest_file:
        manifest = tomlkit.load(manifest_file)

    manifest["id"] = id
    if name is not None:
        manifest["name"] = name
    if description is not None:
        manifest["description"] = description
    if version is not None:
        manifest["version"] = version
        semver.Version.parse(manifest["version"])
    if maintainer is not None:
        manifest["maintainer"] = maintainer
        email.utils.parseaddr(manifest["maintainer"])
    if website is not None:
        manifest["website"] = website
    if license is not None:
        manifest["license"] = license
        spdx_license_list.LICENSES[manifest["license"]]

    with open(manifest_path, "w") as manifest_file:
        tomlkit.dump(manifest, manifest_file)

    return plugin_path
