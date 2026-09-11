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
