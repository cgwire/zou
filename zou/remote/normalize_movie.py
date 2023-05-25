#!/usr/bin/env python
import logging
import os
import sys
import tempfile

from zou.remote.config_payload import (
    check_config_version,
    get_config_from_payload,
    get_storage,
    get_file_from_storage,
    put_file_to_storage,
    make_key,
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
    storage = get_storage(config, "movies")

    with tempfile.TemporaryDirectory() as tmpdir:
        preview_file_id = config["preview_file_id"]
        file_path = _fetch_movie_file(storage, tmpdir, preview_file_id)
        (high_def_path, low_def_path, err) = _run_normalize_movie(
            config, file_path
        )

        if err is None:
            put_file_to_storage(
                storage, high_def_path, make_key("previews", preview_file_id)
            )
            put_file_to_storage(
                storage, low_def_path, make_key("lowdef", preview_file_id)
            )
            logger.info(f"Normalization succeded {high_def_path}")
        else:
            logger.error(f"Normalization failed: {err}")
            sys.exit(1)
    return None


def _fetch_movie_file(storage, outdir, preview_file_id):
    """
    Download the movie file.
    """
    prefix = "source"
    filename = f"cache-previews-{preview_file_id}.mp4"
    file_path = os.path.join(outdir, filename)
    return get_file_from_storage(
        storage, file_path, make_key(prefix, preview_file_id)
    )


def _run_normalize_movie(config, movie_path):
    return normalize_movie(
        movie_path, config["fps"], config["width"], config["height"]
    )


if __name__ == "__main__":
    main()
