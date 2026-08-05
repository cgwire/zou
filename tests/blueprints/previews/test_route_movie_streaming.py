import os

from tests.base import ApiDBTestCase


class MovieStreamingRoutesTestCase(ApiDBTestCase):
    """
    Upload a real movie (normalization disabled so the original file is
    stored as-is) then stream it back through the movie routes.
    """

    def setUp(self):
        super(MovieStreamingRoutesTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.movie_path = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )

    def upload_movie_preview(self):
        comment = self.post(
            f"/actions/tasks/{self.task_id}/comment/",
            {"task_status_id": self.wip_status_id, "comment": "c"},
        )
        preview_file = self.post(
            f"/actions/tasks/{self.task_id}"
            f"/comments/{comment['id']}/add-preview",
            {},
        )
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

    def test_stream_unknown_movie_returns_404(self):
        self.upload_movie_preview()
        from zou.app.utils import fields

        response = self.app.get(
            f"/movies/originals/preview-files/{fields.gen_uuid()}.mp4",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 404)
