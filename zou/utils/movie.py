from collections import namedtuple
import contextlib
import os
import math
import shutil
import subprocess

import ffmpeg


EncodingParameters = namedtuple('EncodingParameters',
                                ['width', 'height', 'fps'])


def save_file(tmp_folder, instance_id, file_to_save):
    """
    Save given file in given path. This function should only be used for
    temporary storage.
    """
    extension = file_to_save.filename[-4:]
    file_name = instance_id + extension.lower() + ".tmp"
    file_path = os.path.join(tmp_folder, file_name)
    file_to_save.save(file_path)
    return file_path


def generate_thumbnail(movie_path):
    """
    Generate a thumbnail to represent the movie given at movie path. It
    takes a picture at the first frame of the movie.
    """
    folder_path = os.path.dirname(movie_path)
    file_source_name = os.path.basename(movie_path)
    file_target_name = "%s.png" % file_source_name[:-4]
    file_target_path = os.path.join(folder_path, file_target_name)

    ffmpeg.input(movie_path, ss="00:00:00").output(
        file_target_path, vframes=1
    ).run(quiet=True)
    return file_target_path


def generate_tile(movie_path):
    pass


def get_movie_size(movie_path):
    """
    Returns movie resolution (extract a frame and returns its size).
    """
    probe = ffmpeg.probe(movie_path)
    video = next((
        stream for stream in probe['streams']
        if stream['codec_type'] == 'video'
    ), None)
    width = int(video['width'])
    height = int(video['height'])
    return (width, height)


def normalize_movie(movie_path, fps, width, height):
    """
    normalize movie using resolution, width and height given in parameter.
    """
    folder_path = os.path.dirname(movie_path)
    file_source_name = os.path.basename(movie_path)
    file_target_name = "%s.mp4" % file_source_name[:-8]
    file_target_path = os.path.join(folder_path, file_target_name)

    (w, h) = get_movie_size(movie_path)
    resize_factor = w / h

    if width is None:
        width = math.floor(resize_factor * height)

    if width % 2 == 1:
        width = width + 1

    if height % 2 == 1:
        height = height + 1

    stream = ffmpeg.input(movie_path)
    stream = stream.output(
        file_target_path,
        pix_fmt="yuv420p",
        format="mp4",
        r=fps,
        crf="15",
        preset="medium",
        vcodec="libx264",
        vsync="passthrough",
        s="%sx%s" % (width, height),
    )
    stream.run(quiet=False, capture_stderr=True)
    if not has_soundtrack(file_target_path):
        _, _, err = add_empty_soundtrack(file_target_path)
    else:
        err = None
    return file_target_path, err


def add_empty_soundtrack(file_path):
    tmp_file_path = file_path + ".tmp.mp4"

    with contextlib.suppress(FileNotFoundError):
        os.remove(tmp_file_path)

    args = [
        "ffmpeg",
        "-f", "lavfi",
        "-i", "anullsrc",
        "-i", file_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:a",
        "-map", "1:v",
        "-shortest",
        tmp_file_path
    ]
    sp = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, error = sp.communicate()
    err = None
    if error:
        from flask import current_app
        current_app.logger.error(
            "Fail to add silent audiotrack to: %s" % file_path
        )
        err = "\n".join(str(err).split("\\n"))
        current_app.logger.error(err)

    shutil.copyfile(tmp_file_path, file_path)
    return sp.returncode, out, err


def has_soundtrack(file_path):
    audio = ffmpeg.probe(file_path, select_streams='a')
    return len(audio["streams"]) > 0


def build_playlist_movie(tmp_file_paths, movie_file_path, width, height, fps):
    """
    Build a single movie file from a playlist.
    """
    in_files = []
    result = {"message": ""}
    if len(tmp_file_paths) > 0:
        (first_movie_file_path, _) = tmp_file_paths[0]
        if width is None:
            (width, height) = get_movie_size(first_movie_file_path)

        for tmp_file_path, file_name in tmp_file_paths:
            if not has_soundtrack(tmp_file_path):
                ret, _, err = add_empty_soundtrack(tmp_file_path)
                if err:
                    result["message"] += "%s\n" % err
                if ret != 0:
                    result["success"] = False
                    return result

        for tmp_file_path, file_name in tmp_file_paths:
            in_file = ffmpeg.input(tmp_file_path)
            in_files.append(
                in_file["v"]
                .filter("setsar", "1/1")
                .filter("scale", width, height)
            )
            in_files.append(in_file["a"])

        joined = ffmpeg.concat(*in_files, v=1, a=1).node
        video = joined[0]
        audio = joined[1]

        try:
            ffmpeg.output(
                audio, video, movie_file_path
            ).overwrite_output().run()
        except Exception as e:
            print(e)
            result["success"] = False
            result["message"] += str(e)
            return result

    result["success"] = True
    return result
