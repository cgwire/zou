import json
import sys

from pathlib import Path

from zou.remote.storage import ObjectStorageClient, S3Client, SwiftClient

ObjectStorageClient.register(S3Client)
ObjectStorageClient.register(SwiftClient)


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


def get_storage(config):
    if config["FS_BACKEND"] == "s3":
        return S3Client(config)
    elif config["FS_BACKEND"] == "swift":
        return SwiftClient(config)
    else:
        print("Unknown object storage backend (%r)" % config["FS_BACKEND"])
        sys.exit(1)
