import os
import tempfile
from unittest.mock import patch

from PIL import Image

from tests.base import ApiDBTestCase
from zou.app.services import preview_files_service


def _make_white_png(size=(200, 200)):
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.new("RGB", size, (255, 255, 255)).save(path, "PNG")
    return path


def _patch_movie_extraction(test_case, frame_factory):
    """Patch the project/entity/fps lookups and the frame extractor used
    by the bulk-annotation routes so route tests can skip ffmpeg and
    drive the extractor with arbitrary temp PNGs."""
    patches = [
        patch(
            "zou.app.services.preview_files_service.get_project_from_preview_file",
            return_value={"id": "p", "fps": "24"},
        ),
        patch(
            "zou.app.services.preview_files_service.get_entity_from_preview_file",
            return_value=None,
        ),
        patch(
            "zou.app.services.preview_files_service.get_preview_file_fps",
            return_value="24",
        ),
        patch(
            "zou.app.services.preview_files_service.extract_frame_from_preview_file",
            side_effect=lambda pf, fn: frame_factory(),
        ),
    ]
    for p in patches:
        p.start()
        test_case.addCleanup(p.stop)


class ExtractAnnotatedFrameRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        annotation = {
            "time": 9 / 24,
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 10,
                        "top": 10,
                        "width": 20,
                        "height": 20,
                        "stroke": "#ff0000",
                        "strokeWidth": 2,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            },
        }
        preview_files_service.update_preview_file_annotations(
            self.user["id"],
            str(self.project.id),
            self.preview_file["id"],
            additions=[annotation],
        )
        self.url = (
            "/actions/preview-files/"
            f"{self.preview_file['id']}/extract-annotated-frame"
        )

    def _patch_extraction(self, frame_path):
        patches = [
            patch(
                "zou.app.services.preview_files_service.get_project_from_preview_file",
                return_value={"id": "p", "fps": "24"},
            ),
            patch(
                "zou.app.services.preview_files_service.get_entity_from_preview_file",
                return_value=None,
            ),
            patch(
                "zou.app.services.preview_files_service.get_preview_file_fps",
                return_value="24",
            ),
            patch(
                "zou.app.services.preview_files_service.extract_frame_from_preview_file",
                return_value=frame_path,
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_returns_png_when_annotation_matches(self):
        frame_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(frame_path) and os.remove(frame_path)
        )
        self._patch_extraction(frame_path)
        response = self.app.get(
            self.url + "?frame_number=10", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertGreater(len(response.data), 0)

    def test_400_when_no_annotation_at_frame(self):
        frame_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(frame_path) and os.remove(frame_path)
        )
        self._patch_extraction(frame_path)
        response = self.app.get(
            self.url + "?frame_number=200", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 400)

    def test_400_when_frame_number_missing(self):
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 400)

    def test_400_when_frame_number_invalid(self):
        response = self.app.get(
            self.url + "?frame_number=0", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 400)

    def test_404_when_preview_file_id_unknown(self):
        url = (
            "/actions/preview-files/00000000-0000-0000-0000-000000000000"
            "/extract-annotated-frame?frame_number=1"
        )
        response = self.app.get(url, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)

    def test_404_when_preview_binary_missing(self):
        self._patch_extraction(frame_path=None)
        response = self.app.get(
            self.url + "?frame_number=10", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 404)


class ExtractAnnotatedFramePictureRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        # Make the fixture preview look like a picture preview.
        from zou.app.models.preview_file import PreviewFile

        record = PreviewFile.get(self.preview_file["id"])
        record.update({"extension": "png"})
        self.preview_file = record.serialize()
        annotation = {
            "time": 0,
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 10,
                        "top": 10,
                        "width": 20,
                        "height": 20,
                        "stroke": "#ff0000",
                        "strokeWidth": 2,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            },
        }
        preview_files_service.update_preview_file_annotations(
            self.user["id"],
            str(self.project.id),
            self.preview_file["id"],
            additions=[annotation],
        )
        self.url = (
            "/actions/preview-files/"
            f"{self.preview_file['id']}/extract-annotated-frame"
        )

    def _patch_copy(self, picture_path):
        p = patch(
            "zou.app.services.preview_files_service._copy_picture_preview_to_temp_png",
            return_value=picture_path,
        )
        p.start()
        self.addCleanup(p.stop)

    def test_returns_png_for_picture(self):
        picture_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(picture_path) and os.remove(picture_path)
        )
        self._patch_copy(picture_path)
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertGreater(len(response.data), 0)

    def test_frame_number_is_accepted_but_ignored_for_picture(self):
        picture_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(picture_path) and os.remove(picture_path)
        )
        self._patch_copy(picture_path)
        response = self.app.get(
            self.url + "?frame_number=42", headers=self.base_headers
        )
        self.assertEqual(response.status_code, 200)


class ExtractAllAnnotatedFramesRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        annotations = [
            {
                "time": 0,
                "drawing": {
                    "objects": [
                        {
                            "type": "rect",
                            "left": 10,
                            "top": 10,
                            "width": 20,
                            "height": 20,
                            "stroke": "#ff0000",
                            "strokeWidth": 2,
                            "canvasWidth": 200,
                            "canvasHeight": 200,
                        }
                    ]
                },
            },
            {
                "time": 1,
                "drawing": {
                    "objects": [
                        {
                            "type": "rect",
                            "left": 30,
                            "top": 30,
                            "width": 20,
                            "height": 20,
                            "stroke": "#00ff00",
                            "strokeWidth": 2,
                            "canvasWidth": 200,
                            "canvasHeight": 200,
                        }
                    ]
                },
            },
        ]
        preview_files_service.update_preview_file_annotations(
            self.user["id"],
            str(self.project.id),
            self.preview_file["id"],
            additions=annotations,
        )
        self.url = (
            "/actions/preview-files/"
            f"{self.preview_file['id']}/extract-annotated-frames"
        )

    def test_returns_zip_for_movie(self):
        import io
        import zipfile

        _patch_movie_extraction(self, _make_white_png)
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.data)) as zf:
            self.assertEqual(len(zf.namelist()), 2)
            self.assertTrue(
                all(n.endswith(".png") for n in zf.namelist()),
                zf.namelist(),
            )

    def test_400_when_no_annotations(self):
        from zou.app.models.preview_file import PreviewFile
        from zou.app.services import files_service

        record = PreviewFile.get(self.preview_file["id"])
        record.update({"annotations": []})
        files_service.clear_preview_file_cache(self.preview_file["id"])
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 400)

    def test_404_when_movie_binary_missing(self):
        _patch_movie_extraction(self, lambda: None)
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)


class ExtractAllAnnotatedFramesPdfRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        annotations = [
            {
                "time": 0,
                "drawing": {
                    "objects": [
                        {
                            "type": "rect",
                            "left": 10,
                            "top": 10,
                            "width": 20,
                            "height": 20,
                            "stroke": "#ff0000",
                            "strokeWidth": 2,
                            "canvasWidth": 200,
                            "canvasHeight": 200,
                        }
                    ]
                },
            },
            {
                "time": 1,
                "drawing": {
                    "objects": [
                        {
                            "type": "rect",
                            "left": 30,
                            "top": 30,
                            "width": 20,
                            "height": 20,
                            "stroke": "#00ff00",
                            "strokeWidth": 2,
                            "canvasWidth": 200,
                            "canvasHeight": 200,
                        }
                    ]
                },
            },
        ]
        preview_files_service.update_preview_file_annotations(
            self.user["id"],
            str(self.project.id),
            self.preview_file["id"],
            additions=annotations,
        )
        self.url = (
            "/actions/preview-files/"
            f"{self.preview_file['id']}/extract-annotated-frames-pdf"
        )

    def test_returns_pdf_for_movie(self):
        _patch_movie_extraction(self, _make_white_png)
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF-"))

    def test_400_when_no_annotations(self):
        from zou.app.models.preview_file import PreviewFile
        from zou.app.services import files_service

        record = PreviewFile.get(self.preview_file["id"])
        record.update({"annotations": []})
        files_service.clear_preview_file_cache(self.preview_file["id"])
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 400)

    def test_404_when_movie_binary_missing(self):
        _patch_movie_extraction(self, lambda: None)
        response = self.app.get(self.url, headers=self.base_headers)
        self.assertEqual(response.status_code, 404)
