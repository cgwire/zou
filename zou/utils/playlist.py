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
    EncodingParameters,
    build_playlist_movie,
    concat_demuxer,
    concat_filter
)


ObjectStorageClient.register(S3Client)
ObjectStorageClient.register(SwiftClient)


def fetch_inputs(storage, outdir, preview_file_ids, bucket_prefix):
    """Fetch inputs from object storage, return a list of local paths"""
    input_paths = []
    for input_id in preview_file_ids:
        prefix = "previews"
        bucket = "movies"
        filename = "cache-previews-%s.mp4" % input_id
        file_path = Path(outdir) / filename
        if not file_path.exists() or os.path.getsize(file_path) == 0:
            with open(file_path, "wb") as output:
                key = "%s-%s" % (prefix, input_id)
                storage.get(bucket_prefix + bucket, key, output)
        input_paths.append((str(file_path), filename))
    return input_paths


def _run_build_playlist(input_paths, output_movie_path, enc_params):
    is_build_successful = False
    try:
        result = build_playlist_movie(
            concat_demuxer,
            input_paths,
            output_movie_path,
            **enc_params._asdict()
        )
        if result["success"] and os.path.exists(output_movie_path):
            is_build_successful = True
    except Exception:
        is_build_successful = False

    if not is_build_successful:
        result = build_playlist_movie(
            concat_filter,
            input_paths,
            output_movie_path,
            **enc_params._asdict()
        )
    return result


def main():
    """
    Generate a playlist from shots, upload generated file in the object
    storage.
    We assume that this script is launched in the context of a Nomad job.
    Arguments are retrieved from a payload file at JSON format.
    Nevertheless this script can be run directly from the command line.
    """
    if len(sys.argv) < 2:
        print("Required parameter is missing.", file=sys.stderr)
        sys.exit(1)

    payload_file = Path(sys.argv[1])
    if not payload_file.exists():
        print("Payload file %r doesn't exist" % sys.argv[1], file=sys.stderr)
        sys.exit(1)

    with payload_file.open() as data:
        config = json.load(data)

    try:
        version = int(config["version"])
    except (ValueError, KeyError):
        version = None

    if version is None or version > 1:
        print("Input parameters: unsupported format (version: %r)" % version,
              file=sys.stderr)
        sys.exit(1)

    if config["FS_BACKEND"] == "s3":
        storage = S3Client(config)
    elif config["FS_BACKEND"] == "swift":
        storage = SwiftClient(config)
    else:
        print("Unknown object storage backend (%r)" % config["FS_BACKEND"])
        sys.exit(1)

    bucket_prefix = config["bucket_prefix"]
    with tempfile.TemporaryDirectory() as tmpdir:
        enc_params = EncodingParameters(
            width=config["width"],
            height=config["height"],
            fps=config["fps"]
        )

        input_zipped = base64.b64decode(config["input"])
        preview_file_ids = json.loads(zlib.decompress(input_zipped))
        input_paths = fetch_inputs(
            storage,
            tmpdir,
            preview_file_ids,
            bucket_prefix
        )

        output_movie_path = str(Path(tmpdir) / config["output_filename"])
        result = _run_build_playlist(
            input_paths,
            output_movie_path,
            enc_params
        )

        if result["success"]:
            storage.put(
                output_movie_path,
                bucket_prefix + "movies",
                config["output_key"]
            )
        else:
            print("Playlist creation failed: %s" % result.get('message'),
                  file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
