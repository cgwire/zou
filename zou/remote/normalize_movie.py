#!/usr/bin/env python
import logging
import os
import sys
import tempfile

from pathlib import Path
from zou.remote.config_payload import (
    check_config_version,
    get_config_from_payload,
    get_storage,
)

from zou.utils.movie import normalize_movie

logging.basicConfig(
    format="%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    """
    Normalize given preview file in two videos
    We assume that this script is launched in the context of a Nomad job.
    Arguments are retrieved from a payload file at JSON format.
    Nevertheless this script can be run directly from the command line.
    """
    config = get_config_from_payload()
    check_config_version(config)
    storage = get_storage(config)

    bucket_prefix = config["bucket_prefix"]
    with tempfile.TemporaryDirectory() as tmpdir:
        preview_file_id = config["preview_file_id"]
        file_path = _fetch_movie_file(
            storage, tmpdir, preview_file_id, bucket_prefix
        )
        (high_def_path, low_def_path, err) = _run_normalize_movie(
            config, file_path
        )

        if err is None:
            storage.put(
                high_def_path,
                bucket_prefix + "movies",
                "previews-" + preview_file_id,
            )
            storage.put(
                low_def_path,
                bucket_prefix + "movies",
                "lowdef-" + preview_file_id,
            )
            logger.info(f"Normalization succeded {high_def_path}")
        else:
            logger.error(f"Normalization failed: {err}")
            sys.exit(1)
    return None


def _fetch_movie_file(storage, outdir, preview_file_id, bucket_prefix):
    """
    Download the movie file.
    """
    prefix = "source"
    bucket = "movies"
    filename = "cache-previews-%s.mp4" % preview_file_id
    file_path = Path(outdir) / filename
    if not file_path.exists() or os.path.getsize(file_path) == 0:
        with open(file_path, "wb") as output:
            key = "%s-%s" % (prefix, preview_file_id)
            storage.get(bucket_prefix + bucket, key, output)
    return str(file_path)


def _run_normalize_movie(config, movie_path):
    return normalize_movie(
        movie_path, config["fps"], config["width"], config["height"]
    )


if __name__ == "__main__":
    main()
