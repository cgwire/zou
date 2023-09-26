#!/usr/bin/env python
import base64
import orjson as json
import logging
import os
import sys
import tempfile
import zlib

from zou.remote.config_payload import (
    check_config_version,
    get_config_from_payload,
    get_storage,
    get_file_from_storage,
    put_file_to_storage,
    make_key,
)

from zou.utils.movie import (
    EncodingParameters,
    build_playlist_movie,
    concat_demuxer,
    concat_filter,
)

logging.basicConfig(
    format="%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def fetch_inputs(storage, outdir, preview_file_ids):
    """Fetch inputs from object storage, return a list of local paths"""
    input_paths = []
    for input_id in preview_file_ids:
        filename = f"cache-previews-{input_id}.mp4"
        file_path = os.path.join(outdir, filename)
        input_paths.append(
            (
                get_file_from_storage(
                    storage, file_path, make_key("previews", input_id)
                ),
                filename,
            )
        )
    return input_paths


def _run_build_playlist(input_paths, output_movie_path, enc_params, full):
    is_build_successful = False
    if not full:
        try:
            result = build_playlist_movie(
                concat_demuxer,
                input_paths,
                output_movie_path,
                **enc_params._asdict(),
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
            **enc_params._asdict(),
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
    config = get_config_from_payload()
    check_config_version(config)
    storage = get_storage(config, "movies")

    with tempfile.TemporaryDirectory() as tmpdir:
        enc_params = EncodingParameters(
            width=config["width"], height=config["height"], fps=config["fps"]
        )

        input_zipped = base64.b64decode(config["input"])
        preview_file_ids = json.loads(zlib.decompress(input_zipped))
        input_paths = fetch_inputs(storage, tmpdir, preview_file_ids)

        output_movie_path = os.path.join(tmpdir, config["output_filename"])
        result = _run_build_playlist(
            input_paths,
            output_movie_path,
            enc_params,
            config["full"] == "true",
        )

        if result["success"]:
            put_file_to_storage(
                storage, output_movie_path, config["output_key"]
            )
        else:
            logger.error(
                "Playlist creation failed: %s" % result.get("message"),
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
