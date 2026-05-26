import os
import tempfile
from unittest.mock import patch

from tests.base import ApiDBTestCase


from zou.app.services import files_service, preview_files_service
from zou.app.services.exception import (
    AnnotationNotFoundException,
    WrongParameterException,
)
from zou.app.services.preview_files_service import (
    _is_valid_resolution,
    _is_valid_partial_resolution,
    extract_all_annotation_frames_from_preview_file,
    extract_all_annotation_frames_pdf_from_preview_file,
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


def _make_red_rect_annotation(canvas_size=200):
    return {
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
                    "canvasWidth": canvas_size,
                    "canvasHeight": canvas_size,
                }
            ]
        },
    }


def _make_white_png(size=(200, 200)):
    from PIL import Image

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.new("RGB", size, (255, 255, 255)).save(path, "PNG")
    return path


def _patch_movie_extraction(
    test_case, frame_factory, file_name="proj_asset_anim_v1.mp4"
):
    """Patch the project/entity/fps lookups and the frame extractor used
    by the bulk-annotation builders so service tests can assert on file
    names and frame numbers without going through ffmpeg."""
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
        patch(
            "zou.app.services.preview_files_service.names_service.get_preview_file_name",
            return_value=file_name,
        ),
    ]
    for p in patches:
        p.start()
        test_case.addCleanup(p.stop)


class ExtractAnnotationFramePictureTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        self.preview_file["extension"] = "png"
        self.preview_file["annotations"] = [_make_red_rect_annotation()]

    def _patch_copy(self, picture_path):
        p = patch(
            "zou.app.services.preview_files_service._copy_picture_preview_to_temp_png",
            return_value=picture_path,
        )
        p.start()
        self.addCleanup(p.stop)

    def test_returns_composited_picture(self):
        from PIL import Image

        picture_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(picture_path) and os.remove(picture_path)
        )
        self._patch_copy(picture_path)
        result = extract_annotation_frame_from_preview_file(self.preview_file)
        self.assertEqual(result, picture_path)
        pixel = Image.open(picture_path).getpixel((10, 20))[:3]
        diffs = [abs(c - e) for c, e in zip(pixel, (255, 0, 0))]
        self.assertLess(max(diffs), 100)

    def test_frame_number_is_ignored_on_picture(self):
        picture_path = _make_white_png()
        self.addCleanup(
            lambda: os.path.exists(picture_path) and os.remove(picture_path)
        )
        self._patch_copy(picture_path)
        # Passing a frame_number with a picture must not raise.
        result = extract_annotation_frame_from_preview_file(
            self.preview_file, frame_number=42
        )
        self.assertEqual(result, picture_path)

    def test_raises_when_no_annotation_on_picture(self):
        self.preview_file["annotations"] = []
        self._patch_copy("/tmp/unused.png")
        with self.assertRaises(AnnotationNotFoundException):
            extract_annotation_frame_from_preview_file(self.preview_file)

    def test_returns_none_when_picture_binary_missing(self):
        self._patch_copy(None)
        result = extract_annotation_frame_from_preview_file(self.preview_file)
        self.assertIsNone(result)

    def test_unsupported_extension_raises(self):
        self.preview_file["extension"] = "psd"
        with self.assertRaises(WrongParameterException):
            extract_annotation_frame_from_preview_file(self.preview_file)

    def test_movie_without_frame_number_raises(self):
        self.preview_file["extension"] = "mp4"
        with self.assertRaises(WrongParameterException):
            extract_annotation_frame_from_preview_file(self.preview_file)


class ExtractAllAnnotationFramesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        self.preview_file["annotations"] = [
            {**_make_red_rect_annotation(), "time": 0},
            {**_make_red_rect_annotation(), "time": 1},
        ]

    def test_movie_zip_contains_one_png_per_annotation(self):
        import zipfile

        def factory():
            return _make_white_png()

        _patch_movie_extraction(self, factory)
        zip_path = extract_all_annotation_frames_from_preview_file(
            self.preview_file
        )
        self.addCleanup(
            lambda: os.path.exists(zip_path) and os.remove(zip_path)
        )
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(zf.namelist())
        # Annotation at time=0 → frame 1; time=1 with fps=24 → frame 25.
        self.assertEqual(
            names,
            [
                "proj_asset_anim_v1_frame_1.png",
                "proj_asset_anim_v1_frame_25.png",
            ],
        )

    def test_raises_when_no_annotations(self):
        self.preview_file["annotations"] = []
        with self.assertRaises(AnnotationNotFoundException):
            extract_all_annotation_frames_from_preview_file(self.preview_file)

    def test_returns_none_when_movie_binary_missing(self):
        _patch_movie_extraction(self, lambda: None)
        result = extract_all_annotation_frames_from_preview_file(
            self.preview_file
        )
        self.assertIsNone(result)

    def test_picture_zip_one_image_per_annotation(self):
        import zipfile

        self.preview_file["extension"] = "png"
        self.preview_file["annotations"] = [
            _make_red_rect_annotation(),
            _make_red_rect_annotation(),
            _make_red_rect_annotation(),
        ]
        patches = [
            patch(
                "zou.app.services.preview_files_service._copy_picture_preview_to_temp_png",
                side_effect=lambda pf: _make_white_png(),
            ),
            patch(
                "zou.app.services.preview_files_service.names_service.get_preview_file_name",
                return_value="proj_asset_anim_v1.png",
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        zip_path = extract_all_annotation_frames_from_preview_file(
            self.preview_file
        )
        self.addCleanup(
            lambda: os.path.exists(zip_path) and os.remove(zip_path)
        )
        with zipfile.ZipFile(zip_path) as zf:
            names = sorted(zf.namelist())
        self.assertEqual(
            names,
            [
                "proj_asset_anim_v1_frame_1.png",
                "proj_asset_anim_v1_frame_2.png",
                "proj_asset_anim_v1_frame_3.png",
            ],
        )

    def test_unsupported_extension_raises(self):
        self.preview_file["extension"] = "psd"
        with self.assertRaises(WrongParameterException):
            extract_all_annotation_frames_from_preview_file(self.preview_file)

    def test_entries_own_unique_temp_files_not_shared_with_extract(self):
        """`extract_frame_from_movie` writes to a deterministic /tmp slot
        per (movie, frame). A concurrent caller extracting the same frame
        (e.g. the single-frame route's `os.remove` finally) can delete
        the file from under us. The bundler must claim each extracted
        frame as its own private temp file before rendering."""
        shared_path = _make_white_png()

        def fake_extract(pf, fn):
            # Always returns the same shared path — simulates ffmpeg
            # overwriting the same /tmp slot.
            return shared_path

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
                side_effect=fake_extract,
            ),
            patch(
                "zou.app.services.preview_files_service.names_service.get_preview_file_name",
                return_value="proj_asset_anim_v1.mp4",
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        # After build, the shared slot is gone (a concurrent caller
        # cleaning up would do this). We simulate by deleting it before
        # the bundling phase happens — but since build runs synchronously
        # and bundle happens right after, we test the invariant
        # differently: each entry path must be unique and NOT the shared
        # path. That alone guarantees concurrent shared-path operations
        # can't corrupt the bundle.
        from zou.app.services.preview_files_service import (
            _build_annotated_frame_entries,
        )

        entries = _build_annotated_frame_entries(self.preview_file)
        try:
            paths = [p for _, p in entries]
            self.assertEqual(
                len(set(paths)), len(paths), "entries share a temp path"
            )
            self.assertNotIn(shared_path, paths)
        finally:
            for _, p in entries:
                if os.path.exists(p):
                    os.remove(p)
            if os.path.exists(shared_path):
                os.remove(shared_path)

    def test_skips_annotation_when_ffmpeg_produces_no_file(self):
        """`extract_frame_from_movie` can return a path to a file ffmpeg
        never actually wrote (e.g. when frame_number is past EOF: ffmpeg
        exits 0 with no output). The bundler must NOT crash with
        FileNotFoundError — it skips the annotation and keeps going."""
        import zipfile

        good_path = _make_white_png()
        call_count = {"n": 0}

        def fake_extract(pf, fn):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First annotation succeeds.
                return good_path
            # Second annotation: ffmpeg-silent-fail — returns a path
            # whose file doesn't exist.
            return "/tmp/this-file-does-not-exist-zzzzz.png"

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
                side_effect=fake_extract,
            ),
            patch(
                "zou.app.services.preview_files_service.names_service.get_preview_file_name",
                return_value="proj_asset_anim_v1.mp4",
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        zip_path = extract_all_annotation_frames_from_preview_file(
            self.preview_file
        )
        self.addCleanup(
            lambda: os.path.exists(zip_path) and os.remove(zip_path)
        )
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        # Only the first annotation's frame should be in the archive.
        self.assertEqual(len(names), 1)


class ExtractAllAnnotationFramesPdfTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        self.preview_file["annotations"] = [
            {**_make_red_rect_annotation(), "time": 0},
            {**_make_red_rect_annotation(), "time": 1},
        ]

    def test_pdf_starts_with_pdf_magic(self):
        _patch_movie_extraction(self, _make_white_png)
        pdf_path = extract_all_annotation_frames_pdf_from_preview_file(
            self.preview_file
        )
        self.addCleanup(
            lambda: os.path.exists(pdf_path) and os.remove(pdf_path)
        )
        with open(pdf_path, "rb") as f:
            magic = f.read(5)
        self.assertEqual(magic, b"%PDF-")
        self.assertGreater(os.path.getsize(pdf_path), 1024)

    def test_pdf_has_one_page_per_annotation(self):
        import re

        _patch_movie_extraction(self, _make_white_png)
        pdf_path = extract_all_annotation_frames_pdf_from_preview_file(
            self.preview_file
        )
        self.addCleanup(
            lambda: os.path.exists(pdf_path) and os.remove(pdf_path)
        )
        # Read /Count from the PDF catalog — set by Pillow to the page
        # count when saving with save_all. Avoids depending on a PDF lib.
        with open(pdf_path, "rb") as f:
            data = f.read()
        counts = re.findall(rb"/Count\s+(\d+)", data)
        self.assertIn(b"2", counts)

    def test_raises_when_no_annotations(self):
        self.preview_file["annotations"] = []
        with self.assertRaises(AnnotationNotFoundException):
            extract_all_annotation_frames_pdf_from_preview_file(
                self.preview_file
            )

    def test_returns_none_when_binary_missing(self):
        _patch_movie_extraction(self, lambda: None)
        result = extract_all_annotation_frames_pdf_from_preview_file(
            self.preview_file
        )
        self.assertIsNone(result)

    def test_unsupported_extension_raises(self):
        self.preview_file["extension"] = "psd"
        with self.assertRaises(WrongParameterException):
            extract_all_annotation_frames_pdf_from_preview_file(
                self.preview_file
            )
