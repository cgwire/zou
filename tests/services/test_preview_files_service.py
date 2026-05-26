import os
import tempfile
from unittest.mock import patch

from tests.base import ApiDBTestCase


from zou.app.services import files_service, preview_files_service
from zou.app.services.exception import AnnotationNotFoundException
from zou.app.services.preview_files_service import (
    _is_valid_resolution,
    _is_valid_partial_resolution,
    extract_annotation_frame_from_preview_file,
    extract_frame_from_preview_file,
    extract_tile_from_preview_file,
    get_preview_file_dimensions,
    get_preview_file_fps,
)


class PlaylistTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistTestCase, self).setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.user_id = self.user["id"]
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.annotations_1 = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj1", "type": "path", "path": ["Q", 0, 10]}
                    ]
                },
            }
        ]
        self.annotations_2 = [
            {
                "time": "2",
                "drawing": {
                    "objects": [
                        {"id": "obj2", "type": "path", "path": ["Q", 1, 11]}
                    ]
                },
            }
        ]
        self.annotations_3 = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj3", "type": "path", "path": ["Q", 1, 11]}
                    ]
                },
            }
        ]

    def tearDown(self):
        super(PlaylistTestCase, self).tearDown()
        self.delete_test_folder()

    def test_add_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )

    def test_add_annotations_different_time(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_2,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1 + self.annotations_2,
            persisted_preview_file["annotations"],
        )

    def test_add_annotations_different_objects(self):
        expected_result = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        self.annotations_1[0]["drawing"]["objects"][0],
                        self.annotations_3[0]["drawing"]["objects"][0],
                    ]
                },
            }
        ]
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_3,
        )
        annotations = files_service.get_preview_file(preview_file["id"])[
            "annotations"
        ]
        self.assertEqual(expected_result, annotations)
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_3,
        )
        annotations = files_service.get_preview_file(preview_file["id"])[
            "annotations"
        ]
        self.assertEqual(expected_result, annotations)

    def test_delete_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "2", "objects": ["obj1"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "0", "objects": ["obj4"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "0", "objects": ["obj1"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            [],
            persisted_preview_file["annotations"],
        )

    def test_update_annotations(self):
        self.modifications = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj1", "type": "path", "path": ["Q", 2, 14]}
                    ]
                },
            }
        ]
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1 + self.annotations_2,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            updates=self.modifications,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.modifications + self.annotations_2,
            persisted_preview_file["annotations"],
        )

    def test_update_annotations_aborts_when_lock_unavailable(self):
        """When the Redis lock can't be acquired (Redis down or wait
        timeout exceeded), the service must surface a 503 instead of
        silently racing through the read-modify-write without
        serialization."""
        from contextlib import contextmanager

        from zou.app.services.exception import AnnotationLockTimeoutException

        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )

        @contextmanager
        def unavailable_lock(*args, **kwargs):
            yield False

        with patch(
            "zou.app.services.preview_files_service." "with_preview_file_lock",
            side_effect=unavailable_lock,
        ):
            self.assertRaises(
                AnnotationLockTimeoutException,
                preview_files_service.update_preview_file_annotations,
                self.user_id,
                self.project_id,
                preview_file["id"],
                additions=self.annotations_2,
            )

        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )

    def test_get_preview_file_dimensions(self):
        self.assertFalse(_is_valid_resolution(""))
        self.assertFalse(_is_valid_resolution(None))
        self.assertTrue(_is_valid_resolution("203x121"))
        self.assertTrue(_is_valid_resolution("1920x1080"))
        self.assertTrue(_is_valid_resolution("3840x2160"))
        self.assertFalse(_is_valid_partial_resolution("3840x2160"))
        self.assertTrue(_is_valid_partial_resolution("x2160"))
        project = self.project.serialize()
        entity = self.asset.serialize()
        dimensions = get_preview_file_dimensions(project, entity)
        self.assertEqual(dimensions, (1920, 1080))
        project["resolution"] = "x2160"
        dimensions = get_preview_file_dimensions(project, entity)
        self.assertEqual(dimensions, (None, 2160))
        project["resolution"] = "3840x2160"
        dimensions = get_preview_file_dimensions(project, entity)
        self.assertEqual(dimensions, (3840, 2160))
        entity["data"] = {"resolution": "800x600"}
        dimensions = get_preview_file_dimensions(project, entity)
        self.assertEqual(dimensions, (800, 600))

    def test_get_preview_file_fps(self):
        fps = get_preview_file_fps({"fps": "24.00"})
        self.assertEqual(fps, "24.000")
        fps = get_preview_file_fps({})
        self.assertEqual(fps, "25.000")
        fps = get_preview_file_fps({"fps": None})
        self.assertEqual(fps, "25.000")

    def test_get_last_preview_file_for_task(self):
        preview_file = self.generate_fixture_preview_file()
        preview_file = preview_files_service.get_last_preview_file_for_task(
            self.task_id
        )
        self.assertEqual(preview_file["revision"], 1)

        preview_file = self.generate_fixture_preview_file(revision=2)
        preview_file = preview_files_service.get_last_preview_file_for_task(
            self.task_id
        )
        self.assertEqual(preview_file["revision"], 2)

        preview_file = self.generate_fixture_preview_file(revision=3)
        preview_file = preview_files_service.get_last_preview_file_for_task(
            self.task_id
        )
        self.assertEqual(preview_file["revision"], 3)

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.normalize_movie")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_prepare_and_store_movie_saves_original_metadata(
        self,
        mock_add_movie,
        mock_normalize,
        mock_gen_thumbnail,
        mock_turn_thumbnail,
        mock_save_variants,
        mock_gen_tile,
    ):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)

        # Create a small temp file to act as the uploaded movie
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        uploaded_path = tmp.name

        # Create temp files for normalized outputs
        norm_path = uploaded_path + "_norm.mp4"
        norm_low_path = uploaded_path + "_norm_low.mp4"
        for p in (norm_path, norm_low_path):
            with open(p, "wb") as f:
                f.write(b"\x00" * 512)

        mock_normalize.return_value = (norm_path, norm_low_path, None)
        mock_gen_thumbnail.return_value = norm_path
        mock_gen_tile.return_value = norm_path

        original_width = 720
        original_height = 1280
        original_duration = 42.5
        normalized_width = 1920
        normalized_height = 1080

        with patch(
            "zou.app.services.preview_files_service.movie.get_movie_size"
        ) as mock_size, patch(
            "zou.app.services.preview_files_service.movie.get_movie_duration"
        ) as mock_duration:

            call_count = {"size": 0}

            def size_side_effect(path, **kwargs):
                call_count["size"] += 1
                if call_count["size"] == 1:
                    # First call: reading original file metadata
                    return (original_width, original_height)
                else:
                    # Second call: reading normalized file metadata
                    return (normalized_width, normalized_height)

            mock_size.side_effect = size_side_effect

            duration_call_count = {"n": 0}

            def duration_side_effect(path=None, **kwargs):
                duration_call_count["n"] += 1
                if duration_call_count["n"] == 1:
                    return original_duration
                else:
                    return 40.0

            mock_duration.side_effect = duration_side_effect

            preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )

        persisted = files_service.get_preview_file(preview_file_id)

        # The width/height fields reflect the normalized output
        self.assertEqual(persisted["width"], normalized_width)
        self.assertEqual(persisted["height"], normalized_height)

        # The data field preserves the original metadata
        self.assertIsNotNone(persisted["data"])
        self.assertEqual(persisted["data"]["original_width"], original_width)
        self.assertEqual(persisted["data"]["original_height"], original_height)
        self.assertEqual(
            persisted["data"]["original_duration"], original_duration
        )
        self.assertEqual(persisted["data"]["original_file_size"], 1024)

        # Clean up
        for p in (uploaded_path, norm_path, norm_low_path):
            if os.path.exists(p):
                os.remove(p)

    def test_extract_skips_metadata_only_previews(self):
        """Imported-only previews have no local binary — extract functions
        must short-circuit silently (return None) so callers can no-op
        instead of crashing on FileNotFoundError."""
        preview_file = {
            "id": "some-uuid",
            "extension": "mp4",
            "data": {"imported_only": True},
        }
        self.assertIsNone(extract_frame_from_preview_file(preview_file, 1))
        self.assertIsNone(extract_tile_from_preview_file(preview_file))


class ExtractAnnotationFrameTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        self.preview_file["annotations"] = [
            {
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
        ]

    def _patch_dependencies(self, frame_path=None):
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

    def test_raises_when_no_annotation_matches(self):
        self.preview_file["annotations"] = []
        self._patch_dependencies(frame_path="/tmp/nope.png")
        with self.assertRaises(AnnotationNotFoundException):
            extract_annotation_frame_from_preview_file(self.preview_file, 10)

    def test_raises_when_frame_outside_tolerance(self):
        self._patch_dependencies(frame_path="/tmp/nope.png")
        with self.assertRaises(AnnotationNotFoundException):
            extract_annotation_frame_from_preview_file(self.preview_file, 99)

    def test_returns_composited_path_when_match(self):
        from PIL import Image

        fd, frame_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        Image.new("RGB", (200, 200), (255, 255, 255)).save(frame_path, "PNG")
        self.addCleanup(
            lambda: os.path.exists(frame_path) and os.remove(frame_path)
        )
        self._patch_dependencies(frame_path=frame_path)
        result = extract_annotation_frame_from_preview_file(
            self.preview_file, 10
        )
        self.assertEqual(result, frame_path)
        # Renderer supersamples + LANCZOS-downsamples, so edges are AA.
        # (10, 20) sits on the left outline of a stroke-only rect, with
        # tolerance for the softened red.
        pixel = Image.open(frame_path).getpixel((10, 20))[:3]
        diffs = [abs(c - e) for c, e in zip(pixel, (255, 0, 0))]
        self.assertLess(max(diffs), 100, f"got {pixel}")

    def test_returns_none_when_binary_missing_but_annotation_present(self):
        self._patch_dependencies(frame_path=None)
        result = extract_annotation_frame_from_preview_file(
            self.preview_file, 10
        )
        self.assertIsNone(result)
