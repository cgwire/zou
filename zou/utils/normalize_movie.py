#!/usr/bin/env python
import base64
import json
import os
import sys
import tempfile
import zlib

from pathlib import Path
from zou.utils.storage import ObjectStorageClient, S3Client, SwiftClient


from zou.utils.movie import (
    normalize_movie
)

ObjectStorageClient.register(S3Client)
ObjectStorageClient.register(SwiftClient)


def fetch_movie_file(storage, outdir, preview_file_id, bucket_prefix):
    """Fetch inputs from object storage, return a list of local paths"""
    prefix = "previews"
    bucket = "source-movies"
    filename = "cache-previews-%s.mp4" % preview_file_id
    file_path = Path(outdir) / filename
    if not file_path.exists() or os.path.getsize(file_path) == 0:
        with open(file_path, "wb") as output:
            key = "%s-%s" % (prefix, preview_file_id)
            storage.get(bucket_prefix + bucket, key, output)
    return (str(file_path), filename)


def _get_config_from_payload():
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


def _check_config_version(config):
    try:
        version = int(config["version"])
    except (ValueError, KeyError):
        version = None
    if version is None or version > 1:
        print("Input parameters: unsupported format (version: %r)" % version,
              file=sys.stderr)
        sys.exit(1)
    return version


def _run_normalize_movie(config, output_movie_path):
    return normalize_movie(
        output_movie_path,
        config["fps"],
        config["width"],
        config["height"]
    )


def main():
    """
    Normalize given preview file in two videos
    We assume that this script is launched in the context of a Nomad job.
    Arguments are retrieved from a payload file at JSON format.
    Nevertheless this script can be run directly from the command line.
    """
    config = _get_config_from_payload()
    _check_config_version(config)

    if config["FS_BACKEND"] == "s3":
        storage = S3Client(config)
    elif config["FS_BACKEND"] == "swift":
        storage = SwiftClient(config)
    else:
        print("Unknown object storage backend (%r)" % config["FS_BACKEND"])
        sys.exit(1)

    bucket_prefix = config["bucket_prefix"]
    with tempfile.TemporaryDirectory() as tmpdir:
        preview_file_id = config["preview_file_id"]
        file_path = fetch_movie_file(
            storage,
            tmpdir,
            preview_file_id,
            bucket_prefix
        )

        filename = "cache-previews-%s.mp4" % preview_file_id
        output_movie_path = str(Path(tmpdir)) / filename
        (high_def_path, low_def_path, err) = _run_normalize_movie(
            config,
            file_path,
            output_movie_path
        )

        if err is None:
            storage.put(
                high_def_path,
                bucket_prefix + "movies",
                config["output_key"]
            )
            storage.put(
                high_def_path,
                bucket_prefix + "lowdef",
                config["output_key"]
            )
        else:
            print("Normalization failed: %s" % err,
                  file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
