import os
import tempfile
from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app.blueprints.previews.resources import BaseNewPreviewFilePicture
from zou.app.services.exception import WrongParameterException


class PreviewFilesTestCase(ApiDBTestCase):
    def setUp(self):
        super(PreviewFilesTestCase, self).setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()

    def test_get_running_preview_filless(self):
        self.generate_fixture_preview_file().serialize()
        preview_file_broken = self.generate_fixture_preview_file(
            revision=2, status="broken"
        ).serialize()
        preview_file_processing = self.generate_fixture_preview_file(
            revision=3, status="processing"
        ).serialize()
        preview_files = self.get("data/playlists/preview-files/running")
        self.assertEqual(len(preview_files), 2)
        self.assertEqual(preview_files[0]["id"], preview_file_processing["id"])
        self.assertEqual(preview_files[1]["id"], preview_file_broken["id"])


class _StubPreviewHandler(BaseNewPreviewFilePicture):
    def get_no_job(self):
        return False


class SaveMoviePreviewValidationTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.handler = _StubPreviewHandler()

    def test_raises_when_uploaded_movie_path_missing(self):
        missing_path = "/tmp/zou-test-missing-uploaded-movie.mp4"
        if os.path.exists(missing_path):
            os.remove(missing_path)
        with patch(
            "zou.app.blueprints.previews.resources.movie.save_file",
            return_value=missing_path,
        ):
            self.assertRaises(
                WrongParameterException,
                self.handler.save_movie_preview,
                "preview-id",
                None,
            )

    def test_raises_when_uploaded_movie_path_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            empty_path = tmp.name
        try:
            self.assertEqual(os.path.getsize(empty_path), 0)
            with patch(
                "zou.app.blueprints.previews.resources.movie.save_file",
                return_value=empty_path,
            ):
                self.assertRaises(
                    WrongParameterException,
                    self.handler.save_movie_preview,
                    "preview-id",
                    None,
                )
        finally:
            if os.path.exists(empty_path):
                os.remove(empty_path)
