import os

from unittest.mock import patch

from tests.base import ApiDBTestCase
from zou.app.blueprints.previews import resources as preview_resources
from zou.app.services import files_service
from zou.app.stores import file_store


class MovieStreamingRoutesTestCase(ApiDBTestCase):
    """
    Upload a real movie (normalization disabled so the original file is
    stored as-is) then stream it back through the movie routes.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_task_status_wip()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.movie_path = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )

    def upload_movie_preview(self, save_source_file=False):
        comment = self.post(
            f"/actions/tasks/{self.task_id}/comment/",
            {"task_status_id": self.wip_status_id, "comment": "c"},
        )
        preview_file = self.post(
            f"/actions/tasks/{self.task_id}"
            f"/comments/{comment['id']}/add-preview",
            {},
        )
        with patch.object(
            preview_resources.config,
            "PREVIEW_SAVE_SOURCE_FILE",
            save_source_file,
        ):
            self.upload_file(
                f"/pictures/preview-files/{preview_file['id']}?normalize=false",
                self.movie_path,
            )
        return preview_file["id"]

    def test_stream_original_and_low_movie(self):
        preview_file_id = self.upload_movie_preview()
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()

        response = self.app.get(
            f"/movies/originals/preview-files/{preview_file_id}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "video/mp4")
        self.assertEqual(response.data, movie_content)

        response = self.app.get(
            f"/movies/low/preview-files/{preview_file_id}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, movie_content)

    def test_download_original_movie(self):
        preview_file_id = self.upload_movie_preview()
        response = self.app.get(
            f"/movies/originals/preview-files/{preview_file_id}/download",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "attachment", response.headers.get("Content-Disposition", "")
        )

    def test_stream_falls_back_on_the_source_movie(self):
        """
        Keeping the source and skipping the normalization leaves it as the
        only stored movie: both routes must serve it instead of answering a
        404, and nothing is copied under the previews prefix.
        """
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()

        self.assertFalse(
            os.path.exists(
                file_store.get_local_movie_path("previews", preview_file_id)
            )
        )

        for url in [
            f"/movies/originals/preview-files/{preview_file_id}.mp4",
            f"/movies/low/preview-files/{preview_file_id}.mp4",
        ]:
            response = self.app.get(url, headers=self.base_headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, movie_content)

    def test_source_route_serves_the_source_only(self):
        """
        The sync between two instances needs the source told apart from the
        encoded versions, so this route has no fallback.
        """
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()

        with_source = self.upload_movie_preview(save_source_file=True)
        response = self.app.get(
            f"/movies/source/preview-files/{with_source}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "video/mp4")
        self.assertEqual(response.data, movie_content)

        # Same movie, stored under the previews prefix this time: the route
        # does not fall back on it.
        without_source = self.upload_movie_preview(save_source_file=False)
        response = self.app.get(
            f"/movies/source/preview-files/{without_source}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 404)
        response = self.app.get(
            f"/movies/originals/preview-files/{without_source}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)

    def test_stream_unknown_movie_returns_404(self):
        self.upload_movie_preview()
        from zou.app.utils import fields

        response = self.app.get(
            f"/movies/originals/preview-files/{fields.gen_uuid()}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_stored_movie_prefixes_are_recorded(self):
        """
        Which prefix holds the movie is known when it is stored: recording
        it spares the movie routes from probing the storage on every read.
        """
        with_source = self.upload_movie_preview(save_source_file=True)
        preview_file = files_service.get_preview_file(with_source)
        self.assertEqual(
            preview_file["data"][files_service.MOVIE_PREFIXES_KEY],
            ["source"],
        )

        without_source = self.upload_movie_preview(save_source_file=False)
        preview_file = files_service.get_preview_file(without_source)
        self.assertEqual(
            preview_file["data"][files_service.MOVIE_PREFIXES_KEY],
            ["previews"],
        )

    def recorded_prefixes(self, preview_file_id):
        return files_service.get_preview_file_for_access(preview_file_id)[
            "movie_prefixes"
        ]

    def record_prefixes(self, preview_file_id, prefixes):
        preview_file = files_service.get_preview_file_raw(preview_file_id)
        preview_file.update(
            {"data": {files_service.MOVIE_PREFIXES_KEY: prefixes}}
        )
        files_service.clear_preview_file_cache(preview_file_id)

    def get_movie(self, preview_file_id):
        return self.app.get(
            f"/movies/originals/preview-files/{preview_file_id}.mp4",
            headers=self.base_headers,
        )

    def test_recorded_prefixes_spare_the_storage_probe(self):
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        with patch.object(file_store, "exists_movie") as exists_movie:
            self.assertEqual(self.get_movie(preview_file_id).status_code, 200)
            exists_movie.assert_not_called()

    def test_missing_record_is_probed_once_then_written_back(self):
        # A preview file stored before the record existed.
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        preview_file = files_service.get_preview_file_raw(preview_file_id)
        preview_file.update({"data": {"original_width": 1}})
        files_service.clear_preview_file_cache(preview_file_id)

        with patch.object(
            file_store, "exists_movie", wraps=file_store.exists_movie
        ) as exists_movie:
            self.assertEqual(self.get_movie(preview_file_id).status_code, 200)
            self.assertEqual(exists_movie.call_count, 3)
            self.assertEqual(self.get_movie(preview_file_id).status_code, 200)
            self.assertEqual(exists_movie.call_count, 3)
        self.assertEqual(
            files_service.get_preview_file(preview_file_id)["data"],
            {
                "original_width": 1,
                files_service.MOVIE_PREFIXES_KEY: ["source"],
            },
        )

    def test_stale_record_is_fixed_on_fallback(self):
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        self.record_prefixes(preview_file_id, ["previews"])

        self.assertEqual(self.get_movie(preview_file_id).status_code, 200)
        self.assertEqual(self.recorded_prefixes(preview_file_id), ["source"])

    def test_range_request_uses_a_seekable_file_wrapper(self):
        # gunicorn's wsgi.file_wrapper is not seekable, so Werkzeug used to
        # read the file from the start for every Range request. Hand the
        # route a wrapper that cannot be iterated: the response only works
        # if the route swapped it for Werkzeug's seekable one.
        class NotSeekable:
            def __init__(self, file, *args):
                self.file = file

            def __iter__(self):
                raise AssertionError("range served without seeking")

        preview_file_id = self.upload_movie_preview()
        with open(self.movie_path, "rb") as movie_file:
            movie_file.seek(1000)
            expected = movie_file.read(500)
        response = self.app.get(
            f"/movies/originals/preview-files/{preview_file_id}.mp4",
            headers={**self.base_headers, "Range": "bytes=1000-1499"},
            environ_overrides={"wsgi.file_wrapper": NotSeekable},
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, expected)

    def test_full_file_response_still_fits_gunicorn_sendfile(self):
        # gunicorn hands a response that is an instance of the environ's
        # wsgi.file_wrapper to its sendfile path, which reads `.filelike`
        # on it: the seekable wrapper the route installs must carry it, or
        # every full-file response answers 500 in production.
        preview_file_id = self.upload_movie_preview()
        flask_app = self.app.application
        wsgi_app = flask_app.wsgi_app
        dispatched = []

        def capture_dispatch(environ, start_response):
            respiter = wsgi_app(environ, start_response)
            dispatched.append((environ, respiter))
            return respiter

        with patch.object(flask_app, "wsgi_app", capture_dispatch):
            response = self.app.get(
                f"/movies/originals/preview-files/{preview_file_id}.mp4",
                headers=self.base_headers,
            )
        self.assertEqual(response.status_code, 200)
        environ, respiter = dispatched[0]
        self.assertIsInstance(respiter, environ["wsgi.file_wrapper"])
        self.assertIsInstance(respiter.filelike.fileno(), int)
        response.close()

    def test_cold_cache_download_folds_the_file_name_like_send_file(self):
        # The warm path goes through send_file, which folds a non-ASCII
        # download name to ASCII and adds an RFC 2231 filename*. A raw
        # name on the cold path is an invalid header value for gunicorn.
        preview_file_id = self.upload_movie_preview()
        url = f"/movies/originals/preview-files/{preview_file_id}/download"
        with patch.object(
            preview_resources.names_service,
            "get_preview_file_name",
            return_value="カット 01.mp4",
        ):
            warm = self.app.get(url, headers=self.base_headers)
            with (
                patch.object(
                    preview_resources.file_store,
                    "can_stream_movie_ranges",
                    return_value=True,
                ),
                patch.object(
                    preview_resources.file_store,
                    "read_movie_range",
                    return_value=(2, "bytes 0-1/2", iter([b"ab"])),
                ),
                patch.object(preview_resources.fs, "fill_cache_in_background"),
            ):
                cold = self.app.get(
                    url, headers={**self.base_headers, "Range": "bytes=0-1"}
                )
        self.assertEqual(cold.status_code, 206)
        self.assertIn("filename*=UTF-8''", warm.headers["Content-Disposition"])
        self.assertEqual(
            cold.headers["Content-Disposition"],
            warm.headers["Content-Disposition"],
        )

    def test_cold_cache_without_a_range_fills_then_sends(self):
        # A player asks by range; a whole-file request (download button,
        # gazu, curl) gets one storage read and the validators send_file
        # computes, not two concurrent full GETs and no ETag.
        preview_file_id = self.upload_movie_preview()
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()
        with (
            patch.object(
                preview_resources.file_store,
                "can_stream_movie_ranges",
                return_value=True,
            ),
            patch.object(
                preview_resources.file_store,
                "read_movie_range",
                side_effect=AssertionError("streamed"),
            ),
            patch.object(
                preview_resources.fs,
                "fill_cache_in_background",
                side_effect=AssertionError("filled in background"),
            ),
        ):
            response = self.app.get(
                f"/movies/originals/preview-files/{preview_file_id}.mp4",
                headers=self.base_headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, movie_content)
        self.assertIn("ETag", response.headers)

    def test_cold_cache_fills_only_a_prefix_the_storage_holds(self):
        # The prefix fallback tries prefixes the storage may not hold: a
        # fill started before the range read proved the object exists is
        # a doomed download and a lock file left behind for every miss.
        from flask_fs.errors import FileNotFound

        preview_file_id = self.upload_movie_preview(save_source_file=True)
        self.record_prefixes(preview_file_id, ["previews"])
        fills = []

        def read_movie_range(prefix, id, range_header=None):
            if prefix != "source":
                raise FileNotFound(f"{prefix}-{id}")
            return 2, "bytes 0-1/2", iter([b"ab"])

        with (
            patch.object(
                preview_resources.file_store,
                "can_stream_movie_ranges",
                return_value=True,
            ),
            patch.object(
                preview_resources.file_store,
                "read_movie_range",
                side_effect=read_movie_range,
            ),
            patch.object(
                preview_resources.fs,
                "fill_cache_in_background",
                side_effect=lambda *args: fills.append(args[2]),
            ),
        ):
            response = self.app.get(
                f"/movies/originals/preview-files/{preview_file_id}.mp4",
                headers={**self.base_headers, "Range": "bytes=0-1"},
            )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(fills, ["source"])

    def test_cold_cache_streams_the_range_from_the_storage(self):
        # Remote backend, movie not in the local cache yet: the range is
        # served from the storage right away and one background download
        # fills the cache, instead of the request waiting for the whole
        # file to land on the disk.
        preview_file_id = self.upload_movie_preview()
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()
        fills = []

        def read_movie_range(prefix, id, range_header=None):
            self.assertEqual(range_header, "bytes=1000-1499")
            total = len(movie_content)
            return (
                500,
                f"bytes 1000-1499/{total}",
                iter([movie_content[1000:1500]]),
            )

        with (
            patch.object(
                preview_resources.file_store,
                "can_stream_movie_ranges",
                return_value=True,
            ),
            patch.object(
                preview_resources.file_store,
                "read_movie_range",
                side_effect=read_movie_range,
            ),
            patch.object(
                preview_resources.fs,
                "fill_cache_in_background",
                side_effect=lambda *args: fills.append(args),
            ),
        ):
            response = self.app.get(
                f"/movies/originals/preview-files/{preview_file_id}.mp4",
                headers={**self.base_headers, "Range": "bytes=1000-1499"},
            )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(
            response.headers["Content-Range"],
            f"bytes 1000-1499/{len(movie_content)}",
        )
        self.assertEqual(response.headers["Content-Length"], "500")
        self.assertEqual(response.data, movie_content[1000:1500])
        self.assertNotIn("ETag", response.headers)
        self.assertEqual(len(fills), 1)
        self.assertTrue(fills[0][0].endswith(f"-{preview_file_id}.mp4"))
