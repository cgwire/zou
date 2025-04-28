import tomlkit
import semver
import email.utils
import spdx_license_list
import zipfile

from pathlib import Path
from collections.abc import MutableMapping


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
