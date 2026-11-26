import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from tests.base import ApiDBTestCase
from tests.services.cases import PreviewFileTestCase
from zou.app.exceptions import (
    AnnotationLockTimeoutException,
    AnnotationNotFoundException,
    WrongParameterException,
)
from zou.app.services import files_service, preview_annotations_service
from zou.app.services.preview_annotations_service import (
    extract_all_annotation_frames_from_preview_file,
    extract_all_annotation_frames_pdf_from_preview_file,
    extract_annotation_frame_from_preview_file,
)


class PreviewFileAnnotationsTestCase(PreviewFileTestCase):
    """
    The annotations a preview file carries. Each update is a read, a merge
    and a write, under a lock, addressing drawing objects by id.
    """

    def setUp(self):
        super().setUp()
        self.preview_file_id = str(self.generate_fixture_preview_file().id)
        self.at_zero = [self.annotation("0", "obj1")]
        self.at_two = [self.annotation("2", "obj2")]
        self.also_at_zero = [self.annotation("0", "obj3")]

    def annotation(self, time, object_id, path=None):
        return {
            "time": time,
            "drawing": {
                "objects": [
                    {
                        "id": object_id,
                        "type": "path",
                        "path": path or ["Q", 0, 10],
                    }
                ]
            },
        }

    def annotate(self, **changes):
        """
        Run one annotation update and return what it left on the preview.
        """
        preview_annotations_service.update_preview_file_annotations(
            self.user_id, self.project_id, self.preview_file_id, **changes
        )
        return files_service.get_preview_file(self.preview_file_id)[
            "annotations"
        ]

    def test_a_guest_touches_only_its_own_objects(self):
        self.annotate(additions=self.at_zero)

        def guest_annotates(**changes):
            preview_annotations_service.update_preview_file_annotations(
                "guest",
                self.project_id,
                self.preview_file_id,
                only_own_objects=True,
                **changes,
            )

        guest_annotates(additions=[self.annotation("0", "mine")])
        guest_annotates(
            updates=[self.annotation("0", "obj1", path=["Q", 5, 5])],
            deletions=[{"time": "0", "objects": ["obj1", "mine"]}],
        )

        (annotation,) = files_service.get_preview_file(self.preview_file_id)[
            "annotations"
        ]
        (obj1,) = annotation["drawing"]["objects"]
        self.assertEqual(obj1["id"], "obj1")
        self.assertEqual(obj1["path"], ["Q", 0, 10])
        self.assertNotIn("person_id", obj1)

    def test_an_addition_lands_on_the_preview(self):
        self.assertEqual(self.annotate(additions=self.at_zero), self.at_zero)

    def test_an_addition_at_another_time_is_a_new_entry(self):
        self.annotate(additions=self.at_zero)

        self.assertEqual(
            self.annotate(additions=self.at_two), self.at_zero + self.at_two
        )

    def test_an_addition_at_the_same_time_joins_the_objects(self):
        merged = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        self.at_zero[0]["drawing"]["objects"][0],
                        self.also_at_zero[0]["drawing"]["objects"][0],
                    ]
                },
            }
        ]
        self.annotate(additions=self.at_zero)

        self.assertEqual(self.annotate(additions=self.also_at_zero), merged)
        # Replaying the same addition never doubles nor overwrites.
        self.assertEqual(self.annotate(additions=self.also_at_zero), merged)

    def test_a_deletion_names_a_time_and_the_objects_to_drop(self):
        self.annotate(additions=self.at_zero)

        # Neither an unannotated time nor an unknown object drops anything.
        self.assertEqual(
            self.annotate(deletions=[{"time": "2", "objects": ["obj1"]}]),
            self.at_zero,
        )
        self.assertEqual(
            self.annotate(deletions=[{"time": "0", "objects": ["obj4"]}]),
            self.at_zero,
        )
        # A time left without a single object goes away with them.
        self.assertEqual(
            self.annotate(deletions=[{"time": "0", "objects": ["obj1"]}]), []
        )

    def test_an_update_replaces_the_object_it_names(self):
        modified = [self.annotation("0", "obj1", path=["Q", 2, 14])]
        self.annotate(additions=self.at_zero + self.at_two)

        self.assertEqual(
            self.annotate(updates=modified), modified + self.at_two
        )

    def test_an_update_needs_the_lock(self):
        """
        When the Redis lock cannot be acquired (Redis down, or the wait
        timed out), the update is refused rather than raced through the
        read-modify-write without serialization.
        """
        self.annotate(additions=self.at_zero)

        @contextmanager
        def unavailable_lock(*args, **kwargs):
            yield False

        with patch(
            "zou.app.services.preview_annotations_service.with_preview_file_lock",
            side_effect=unavailable_lock,
        ):
            self.assertRaises(
                AnnotationLockTimeoutException,
                preview_annotations_service.update_preview_file_annotations,
                self.user_id,
                self.project_id,
                self.preview_file_id,
                additions=self.at_two,
            )

        self.assertEqual(
            files_service.get_preview_file(self.preview_file_id)[
                "annotations"
            ],
            self.at_zero,
        )

    def test_normalize_preview_file_annotation_times(self):
        preview_file = files_service.get_preview_file_raw(self.preview_file_id)
        preview_file.update(
            {
                "annotations": [
                    {"time": 0.6, "drawing": {"objects": [{"id": "new-1"}]}},
                    {"time": 0.616, "drawing": {"objects": [{"id": "old-1"}]}},
                ]
            }
        )

        self.assertTrue(
            preview_annotations_service.normalize_preview_file_annotation_times(
                preview_file
            )
        )

        persisted = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(len(persisted["annotations"]), 1)
        self.assertEqual(
            [
                drawing_object["id"]
                for drawing_object in persisted["annotations"][0]["drawing"][
                    "objects"
                ]
            ],
            ["new-1", "old-1"],
        )
        # A second run has nothing left to snap.
        self.assertFalse(
            preview_annotations_service.normalize_preview_file_annotation_times(
                preview_file
            )
        )


class NormalizeAnnotationTimesTestCase(unittest.TestCase):
    """
    Snapping annotation times onto the frame grid the player draws on.
    Two times landing on the same frame become one annotation.
    """

    def normalize(self, annotations, fps=25):
        return preview_annotations_service.normalize_annotation_times(
            annotations, fps
        )

    def test_two_times_on_one_frame_are_merged(self):
        result, changed = self.normalize(
            [
                {
                    "time": 0.6,
                    "frame": 16,
                    "drawing": {"objects": [{"id": "new-1"}]},
                },
                {
                    "time": 0.616,
                    "frame": "017",
                    "drawing": {"objects": [{"id": "old-1"}, {"id": "old-2"}]},
                },
            ]
        )

        self.assertTrue(changed)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["time"], 0.6)
        self.assertEqual(
            [
                drawing_object["id"]
                for drawing_object in result[0]["drawing"]["objects"]
            ],
            ["new-1", "old-1", "old-2"],
        )

    def test_a_merge_keeps_one_object_per_id(self):
        result, _ = self.normalize(
            [
                {"time": 0.6, "drawing": {"objects": [{"id": "a"}]}},
                {
                    "time": 0.616,
                    "drawing": {"objects": [{"id": "a"}, {"id": "b"}]},
                },
            ]
        )

        self.assertEqual(
            [
                drawing_object["id"]
                for drawing_object in result[0]["drawing"]["objects"]
            ],
            ["a", "b"],
        )

    def test_a_time_stored_as_a_string_is_snapped(self):
        result, changed = self.normalize(
            [{"time": "2", "drawing": {"objects": [{"id": "obj-1"}]}}]
        )

        self.assertTrue(changed)
        self.assertEqual(result[0]["time"], 2.0)

    def test_two_frames_apart_are_left_alone(self):
        result, changed = self.normalize(
            [
                {"time": 0.6, "drawing": {"objects": [{"id": "a"}]}},
                {"time": 0.88, "drawing": {"objects": [{"id": "b"}]}},
            ]
        )

        self.assertFalse(changed)
        self.assertEqual(len(result), 2)

    def test_a_time_that_is_not_a_number_is_kept_as_is(self):
        annotations = [{"time": "abc", "drawing": {"objects": [{"id": "a"}]}}]

        result, changed = self.normalize(annotations)

        self.assertFalse(changed)
        self.assertEqual(result, annotations)

    def test_the_annotations_handed_in_are_left_untouched(self):
        annotations = [
            {"time": 0.6, "drawing": {"objects": [{"id": "a"}]}},
            {"time": 0.616, "drawing": {"objects": [{"id": "b"}]}},
        ]

        self.normalize(annotations)

        self.assertEqual(annotations[1]["time"], 0.616)
        self.assertEqual(len(annotations[0]["drawing"]["objects"]), 1)


class ExtractAnnotationFrameTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
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
    """
    Patch the project/entity/fps lookups and the frame extractor used
    by the bulk-annotation builders so service tests can assert on file
    names and frame numbers without going through ffmpeg.
    """
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
            "zou.app.services.preview_files_service.get_preview_file_name",
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
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file().serialize()
        self.preview_file["extension"] = "png"
        self.preview_file["annotations"] = [_make_red_rect_annotation()]

    def _patch_copy(self, picture_path):
        p = patch(
            "zou.app.services.preview_annotations_service._copy_picture_preview_to_temp_png",
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
                "zou.app.services.preview_annotations_service._copy_picture_preview_to_temp_png",
                side_effect=lambda pf: _make_white_png(),
            ),
            patch(
                "zou.app.services.preview_files_service.get_preview_file_name",
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
        """
        `extract_frame_from_movie` writes to a deterministic /tmp slot
        per (movie, frame). A concurrent caller extracting the same frame
        (e.g. the single-frame route's `os.remove` finally) can delete
        the file from under us. The bundler must claim each extracted
        frame as its own private temp file before rendering.
        """
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
                "zou.app.services.preview_files_service.get_preview_file_name",
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
        entries = preview_annotations_service._build_annotated_frame_entries(
            self.preview_file
        )
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
        """
        `extract_frame_from_movie` can return a path to a file ffmpeg
        never actually wrote (e.g. when frame_number is past EOF: ffmpeg
        exits 0 with no output). The bundler must NOT crash with
        FileNotFoundError — it skips the annotation and keeps going.
        """
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
                "zou.app.services.preview_files_service.get_preview_file_name",
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
