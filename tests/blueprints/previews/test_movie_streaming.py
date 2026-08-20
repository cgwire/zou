import os

from unittest.mock import patch

from tests.base import ApiDBTestCase
from zou.app.blueprints.previews import resources as preview_resources
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
        Skipping the normalization can leave the source as the only stored
        movie: both routes must serve it instead of answering a 404.
        """
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()

        os.remove(file_store.get_local_movie_path("previews", preview_file_id))

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
        preview_file_id = self.upload_movie_preview(save_source_file=True)
        with open(self.movie_path, "rb") as movie_file:
            movie_content = movie_file.read()

        response = self.app.get(
            f"/movies/source/preview-files/{preview_file_id}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "video/mp4")
        self.assertEqual(response.data, movie_content)

        os.remove(file_store.get_local_movie_path("source", preview_file_id))

        # The full quality movie is still there, but this route does not
        # fall back on it.
        response = self.app.get(
            f"/movies/source/preview-files/{preview_file_id}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 404)
        response = self.app.get(
            f"/movies/originals/preview-files/{preview_file_id}.mp4",
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
