import os
import json
import sys

from pathlib import Path

from flask_fs import Storage


def get_config_from_payload():
    if len(sys.argv) < 2:
        print("Required parameter is missing.", file=sys.stderr)
        sys.exit(1)

    payload_file = Path(sys.argv[1])
    if not payload_file.exists():
        print("Payload file %r doesn't exist" % sys.argv[1], file=sys.stderr)
        sys.exit(1)

    with payload_file.open() as data:
        config = json.load(data)

    return config


def check_config_version(config):
    try:
        version = int(config["version"])
    except (ValueError, KeyError):
        version = None
    if version is None or version > 1:
        print(
            "Input parameters: unsupported format (version: %r)" % version,
            file=sys.stderr,
        )
        sys.exit(1)
    return version


class FakeApp(object):
    def __init__(self, config):
        self.config = config


def get_storage(config, bucket):
    if config["FS_BACKEND"] not in ["s3", "swift"]:
        print("Unknown object storage backend (%r)" % config["FS_BACKEND"])
        sys.exit(1)

    storage = Storage(
        "%s%s" % (config.get("FS_BUCKET_PREFIX", ""), bucket),
        overwrite=True,
    )
    app = FakeApp(config)
    storage.configure(app)

    return storage


def make_key(prefix, id):
    return f"{prefix}-{id}"


def get_file_from_storage(storage, output_file_path, filename):
    if (
        not os.path.isfile(output_file_path)
        or os.path.getsize(output_file_path) == 0
    ):
        with open(output_file_path, "wb") as output_file:
            output_file.write(storage.read(filename))
    return output_file_path


def put_file_to_storage(storage, input_file_path, filename):
    with open(input_file_path, "rb") as input_file:
        storage.write(filename, input_file)
    return input_file_path
