import json
import logging
import os
import sys

from pathlib import Path

from flask_fs import Storage


def get_config_from_payload():
    if len(sys.argv) < 2:
        print("Required parameter is missing.", file=sys.stderr)
        sys.exit(1)

    payload_file = Path(sys.argv[1])
    if not payload_file.exists():
        print(f"Payload file {sys.argv[1]!r} doesn't exist", file=sys.stderr)
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
            f"Input parameters: unsupported format (version: {version!r})",
            file=sys.stderr,
        )
        sys.exit(1)
    return version


class FakeApp(object):
    def __init__(self, config):
        self.config = config


def get_storage(config, bucket):
    if config["FS_BACKEND"] not in ["s3", "swift"]:
        print(
            f"Unknown object storage backend ({config['FS_BACKEND']!r})",
            file=sys.stderr,
        )
        sys.exit(1)

    storage = Storage(
        f"{config.get('FS_BUCKET_PREFIX', '')}{bucket}",
        overwrite=True,
    )
    app = FakeApp(config)
    storage.configure(app)

    return storage


def make_key(prefix, file_id):
    return f"{prefix}-{file_id}"


def get_file_from_storage(storage, output_file_path, filename):
    if (
        not os.path.isfile(output_file_path)
        or os.path.getsize(output_file_path) == 0
    ):
        with open(output_file_path, "wb") as output_file:
            for chunk in storage.read_chunks(filename):
                output_file.write(chunk)
    return output_file_path


def put_file_to_storage(storage, input_file_path, filename):
    with open(input_file_path, "rb") as input_file:
        storage.write(filename, input_file)
    return input_file_path


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s,%(msecs)d %(levelname)-8s"
        " [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d:%H:%M:%S",
        level=logging.INFO,
    )
    return logging.getLogger(__name__)
