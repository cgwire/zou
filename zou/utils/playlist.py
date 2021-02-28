#!/usr/bin/env python
import base64
import json
import os
import sys
import tempfile
import zlib

from abc import ABCMeta, abstractmethod
from pathlib import Path


from .movie import EncodingParameters, build_playlist_movie, concat_filter


class ObjectStorageClient(metaclass=ABCMeta):
    @abstractmethod
    def put(self, local_path, bucket, key):
        raise NotImplementedError

    @abstractmethod
    def get(self, bucket, key, local_path):
        raise NotImplementedError


class S3Client:
    def __init__(self, config):
        s3connection = dict(
            aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
        )
        if config.get('AWS_DEFAULT_REGION'):
            s3connection['region_name'] = config.get('AWS_DEFAULT_REGION')
        if config.get('S3_ENDPOINT'):
            s3connection['endpoint_url'] = config.get('S3_ENDPOINT')

        import boto3
        self.s3client = boto3.client("s3", **s3connection)

    def get(self, bucket, key, local_fd):
        self.s3client.download_fileobj(bucket, key, local_fd)

    def put(self, local_path, bucket, key):
        self.s3client.upload_file(local_path, bucket, key)


class SwiftClient:
    def __init__(self, config):
        import swiftclient
        self.conn = swiftclient.Connection(
            authurl=config["OS_AUTH_URL"],
            user=config["OS_USERNAME"],
            key=config["OS_PASSWORD"],
            os_options={
                "region_name": config["OS_REGION_NAME"],
                "tenant_name": config["OS_TENANT_NAME"],
            },
            auth_version="3",
        )

    def get(self, bucket, key, local_fd):
        _, data = self.conn.get_object(bucket, key)
        local_fd.write(data)

    def put(self, local_path, bucket, key):
        with open(local_path, 'rb') as local:
            self.conn.put_object(bucket, key, contents=local)


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


ObjectStorageClient.register(S3Client)
ObjectStorageClient.register(SwiftClient)


def main():
    """Generate a playlist from shots, upload generated file in the object
    storage"""
    if len(sys.argv) < 2:
        print("Required parameter is missing.", file=sys.stderr)
        sys.exit(1)

    config_file = Path(sys.argv[1])
    if not config_file.exists():
        print("Config file %r doesn't exist" % sys.argv[1], file=sys.stderr)
        sys.exit(1)

    with config_file.open() as data:
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
        enc_params = EncodingParameters(width=config["width"],
                                        height=config["height"],
                                        fps=config["fps"])

        input_zipped = base64.b64decode(config["input"])
        preview_file_ids = json.loads(zlib.decompress(input_zipped))
        input_paths = fetch_inputs(
            storage,
            tmpdir,
            preview_file_ids,
            bucket_prefix
        )

        output_movie = str(Path(tmpdir) / config["output_filename"])
        result = build_playlist_movie(concat_filter, input_paths, output_movie,
                                      **enc_params._asdict())

        if result["success"]:
            # local file, bucket, remote key
            storage.put(output_movie, bucket_prefix + "movies",
                        config["output_key"])
        else:
            print("Playlist creation failed: %s" % result.get('message'),
                  file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
