#!/usr/bin/env python
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
    setup_logging,
)

from zou.utils.movie import (
    normalize_movie,
    generate_thumbnail,
    generate_tile,
)
from zou.app.utils.thumbnail import (
    turn_into_thumbnail,
    generate_preview_variants,
)

logger = setup_logging()


def main():
    """
    Normalize given preview file in two videos, generate thumbnails
    and tiles.
    We assume that this script is launched in the context of a Nomad
    job. Arguments are retrieved from a payload file at JSON format.
    Nevertheless this script can be run directly from the command line.
    """
    config = get_config_from_payload()
    version = check_config_version(config)
    storage = get_storage(config, "movies")

    with tempfile.TemporaryDirectory() as tmpdir:
        preview_file_id = config["preview_file_id"]
        file_path = _fetch_movie_file(storage, tmpdir, preview_file_id)
        high_def_path, low_def_path, err = _run_normalize_movie(
            config, file_path
        )

        if err is None:
            put_file_to_storage(
                storage,
                high_def_path,
                make_key("previews", preview_file_id),
            )
            put_file_to_storage(
                storage,
                low_def_path,
                make_key("lowdef", preview_file_id),
            )
            logger.info(f"Normalization succeeded {high_def_path}")

            if version >= 2:
                pictures_storage = get_storage(config, "pictures")
                _generate_and_upload_thumbnails(
                    pictures_storage,
                    high_def_path,
                    preview_file_id,
                )
                _generate_and_upload_tile(
                    pictures_storage,
                    high_def_path,
                    preview_file_id,
                )
        else:
            logger.error(f"Normalization failed: {err}")
            sys.exit(1)


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


def _generate_and_upload_thumbnails(
    pictures_storage, movie_path, preview_file_id
):
    """
    Generate thumbnail from movie, resize it, create variants
    (thumbnails, thumbnails-square, previews) and upload all to the
    pictures storage.
    """
    from zou.utils.movie import get_movie_size

    size = get_movie_size(movie_path)
    original_picture_path = generate_thumbnail(movie_path)
    turn_into_thumbnail(original_picture_path, size)

    variants = generate_preview_variants(
        original_picture_path, preview_file_id
    )
    variants.append(("original", original_picture_path))

    for prefix, path in variants:
        put_file_to_storage(
            pictures_storage, path, make_key(prefix, preview_file_id)
        )
        os.remove(path)
    logger.info(f"Thumbnails uploaded for {preview_file_id}")


def _generate_and_upload_tile(pictures_storage, movie_path, preview_file_id):
    """
    Generate tile mosaic from movie and upload to pictures storage.
    """
    try:
        tile_path = generate_tile(movie_path)
        put_file_to_storage(
            pictures_storage,
            tile_path,
            make_key("tiles", preview_file_id),
        )
        os.remove(tile_path)
        logger.info(f"Tile uploaded for {preview_file_id}")
    except Exception:
        logger.error("Failed to create tile", exc_info=True)


if __name__ == "__main__":
    main()
