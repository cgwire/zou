import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.orm.exc import StaleDataError

from tests.base import ApiDBTestCase


from zou.app.models.preview_file import PreviewFile
from zou.app.services import files_service, preview_files_service
from zou.app.stores import file_store
from zou.app.utils import thumbnail as thumbnail_utils
from zou.utils import movie
from zou.app.services.exception import (
    AnnotationLockTimeoutException,
    AnnotationNotFoundException,
    PreviewFileNotFoundException,
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


class PreviewFileTestCase(ApiDBTestCase):
    """
    One task to hang preview files from. Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.user_id = self.user["id"]
        self.generate_fixture_asset()
        self.generate_fixture_task()

    def tearDown(self):
        super().tearDown()
        self.delete_test_folder()


class PreviewFileServiceTestCase(PreviewFileTestCase):
    """
    Everything but the annotations: dimensions, fps, the movie
    preparation and the broken status.
    """

    def test_save_variants_cleans_up_on_upload_failure(self):
        self.generate_fixture_preview_file()
        folder = tempfile.mkdtemp()
        picture_path = os.path.join(folder, "original.png")
        shutil.copyfile(
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            picture_path,
        )
        with patch(
            "zou.app.services.preview_files_service.file_store.add_picture",
            side_effect=RuntimeError("storage down"),
        ):
            with self.assertRaises(RuntimeError):
                preview_files_service.save_variants(
                    str(self.preview_file.id), picture_path
                )
        self.assertEqual(os.listdir(folder), [])

    def test_update_preview_file_drops_its_cache(self):
        # Everything the movie pipeline writes goes through here, and the
        # preview file is read back through a memoized serialization.
        preview_file_id = str(
            self.generate_fixture_preview_file(status="processing").id
        )
        files_service.get_preview_file(preview_file_id)

        preview_files_service.set_preview_file_as_broken(preview_file_id)

        self.assertEqual(
            files_service.get_preview_file(preview_file_id)["status"],
            "broken",
        )

    def test_update_preview_file_raw_deleted_midflight_raises_not_found(self):
        """
        When the row is deleted by another process mid-update, base.update()
        raises StaleDataError then rolls back, which expires the instance.
        Reading preview_file.id in the error handler would then reload the
        deleted row and raise ObjectDeletedError, masking the real error.
        The id must be captured before update() so the handler never touches
        the ORM instance again.

        Modelled with a fake: the test DB harness runs each test in a single
        rolled-back transaction, so a committed cross-process delete (the only
        thing that makes .id reload fail) cannot be reproduced against a real
        row.
        """

        class _VanishingPreviewFile:
            def __init__(self):
                self._live = True

            @property
            def id(self):
                if not self._live:
                    raise AssertionError(
                        "id read after failed update reloads the deleted row"
                    )
                return "50aa09cb-3f13-4c12-8669-e3fb8f0d0ac7"

            def update(self, data):
                # A failed commit rolls back and expires the instance.
                self._live = False
                raise StaleDataError("0 rows matched")

        with self.assertRaises(PreviewFileNotFoundException):
            preview_files_service.update_preview_file_raw(
                _VanishingPreviewFile(), {"status": "broken"}
            )

    def test_a_resolution_is_two_numbers_around_an_x(self):
        self.assertFalse(_is_valid_resolution(""))
        self.assertFalse(_is_valid_resolution(None))
        self.assertTrue(_is_valid_resolution("203x121"))
        self.assertTrue(_is_valid_resolution("1920x1080"))
        self.assertTrue(_is_valid_resolution("3840x2160"))
        # A partial resolution is a height alone, so a full one is not one.
        self.assertFalse(_is_valid_partial_resolution("3840x2160"))
        self.assertTrue(_is_valid_partial_resolution("x2160"))

    def test_get_preview_file_dimensions(self):
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

    def test_get_project_from_preview_file(self):
        preview_file = self.generate_fixture_preview_file()
        project = preview_files_service.get_project_from_preview_file(
            preview_file.id
        )
        self.assertEqual(project["id"], self.project_id)

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

    def test_update_preview_file_position(self):
        """
        Moving a preview within its revision renumbers the whole revision,
        so the positions stay contiguous whichever way it is moved. The
        answer is the revision in its new order.
        """
        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2, name="first")
        preview_file = self.generate_fixture_preview_file(
            revision=2, name="second"
        )
        preview_file_id = str(preview_file.id)
        self.generate_fixture_preview_file(revision=2, name="third")

        def revision_two():
            return (
                PreviewFile.query.filter_by(task_id=self.task_id, revision=2)
                .order_by(PreviewFile.position)
                .all()
            )

        moved = preview_files_service.update_preview_file_position(
            preview_file_id, 1
        )
        preview_files = revision_two()
        self.assertEqual(
            [preview.position for preview in preview_files], [1, 2, 3]
        )
        self.assertEqual(str(preview_files[0].id), preview_file_id)
        self.assertEqual(
            [preview["name"] for preview in moved],
            ["second", "first", "third"],
        )

        moved = preview_files_service.update_preview_file_position(
            preview_file_id, 3
        )
        preview_files = revision_two()
        self.assertEqual(
            [preview.position for preview in preview_files], [1, 2, 3]
        )
        self.assertEqual(str(preview_files[2].id), preview_file_id)
        self.assertEqual(
            [preview["name"] for preview in moved],
            ["first", "third", "second"],
        )

    def test_update_preview_file_position_ignores_a_position_out_of_range(
        self,
    ):
        self.generate_fixture_preview_file(revision=1, name="first")
        second = self.generate_fixture_preview_file(revision=1, name="second")

        for position in [0, 3]:
            with self.subTest(position=position):
                moved = preview_files_service.update_preview_file_position(
                    str(second.id), position
                )
                self.assertEqual(
                    [preview["name"] for preview in moved],
                    ["first", "second"],
                )

    def test_update_preview_file_position_drops_the_caches(self):
        # Every preview of the revision is renumbered, and each one is read
        # through a memoized serialization of its own.
        first = self.generate_fixture_preview_file(revision=1, name="first")
        second = self.generate_fixture_preview_file(revision=1, name="second")
        preview_file_ids = [str(first.id), str(second.id)]
        for preview_file_id in preview_file_ids:
            files_service.get_preview_file(preview_file_id)

        preview_files_service.update_preview_file_position(
            preview_file_ids[1], 1
        )

        self.assertEqual(
            [
                files_service.get_preview_file(preview_file_id)["position"]
                for preview_file_id in preview_file_ids
            ],
            [2, 1],
        )

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

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch("zou.app.services.preview_files_service.movie.normalize_movie")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_prepare_and_store_movie_skip_normalization_full(
        self,
        mock_add_movie,
        mock_normalize,
        mock_size,
        mock_duration,
        mock_gen_thumbnail,
        mock_turn_thumbnail,
        mock_save_variants,
        mock_gen_tile,
    ):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        mock_size.return_value = (1920, 1080)
        mock_duration.return_value = 10.0
        mock_gen_thumbnail.return_value = uploaded_path
        mock_gen_tile.return_value = uploaded_path

        with patch.object(
            preview_files_service.config, "SKIP_NORMALIZATION_FULL", True
        ):
            preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )

        mock_normalize.assert_not_called()
        # Stored once: the low def route falls back on the full quality one.
        self.assertEqual(
            [
                (call.args[0], call.args[2])
                for call in mock_add_movie.mock_calls
            ],
            [("previews", uploaded_path)],
        )
        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch("zou.app.services.preview_files_service.movie.normalize_movie")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_prepare_and_store_movie_skip_normalization_highdef(
        self,
        mock_add_movie,
        mock_normalize,
        mock_size,
        mock_duration,
        mock_gen_thumbnail,
        mock_turn_thumbnail,
        mock_save_variants,
        mock_gen_tile,
    ):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        norm_low_path = self._write_temp_movie()

        mock_normalize.return_value = None, norm_low_path, None
        mock_size.return_value = (1280, 720)
        mock_duration.return_value = 10.0
        mock_gen_thumbnail.return_value = norm_low_path
        mock_gen_tile.return_value = norm_low_path

        with patch.object(
            preview_files_service.config, "SKIP_NORMALIZATION_HIGHDEF", True
        ):
            preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )

        self.assertTrue(mock_normalize.call_args.kwargs["skip_high_def"])
        # Only the low def movie is stored, the thumbnails are built from it.
        self.assertEqual(
            [
                (call.args[0], call.args[2])
                for call in mock_add_movie.mock_calls
            ],
            [("lowdef", norm_low_path)],
        )
        mock_gen_thumbnail.assert_called_once_with(norm_low_path)
        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")
        self.assertEqual(persisted["width"], 1280)

    def _write_temp_movie(self, size=1024):
        """
        Create a non-empty temp file standing in for a movie.
        """
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00" * size)
        tmp.close()
        self.addCleanup(
            lambda: os.path.exists(tmp.name) and os.remove(tmp.name)
        )
        return tmp.name

    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch("zou.app.services.preview_files_service.movie.normalize_movie")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_prepare_and_store_movie_thumbnail_failure_marks_broken(
        self,
        mock_add_movie,
        mock_normalize,
        mock_size,
        mock_duration,
        mock_gen_thumbnail,
    ):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)

        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00" * 1024)
        tmp.close()
        uploaded_path = tmp.name
        norm_path = uploaded_path + "_norm.mp4"
        norm_low_path = uploaded_path + "_norm_low.mp4"
        for p in (norm_path, norm_low_path):
            with open(p, "wb") as f:
                f.write(b"\x00" * 512)

        mock_normalize.return_value = (norm_path, norm_low_path, None)
        mock_size.return_value = (1920, 1080)
        mock_duration.return_value = 10.0
        mock_gen_thumbnail.side_effect = OSError("ffmpeg thumbnail crashed")

        result = preview_files_service.prepare_and_store_movie(
            preview_file_id,
            uploaded_path,
            normalize=True,
            add_source_to_file_store=False,
        )

        self.assertEqual(result["status"], "broken")
        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "broken")
        for p in (uploaded_path, norm_path, norm_low_path):
            self.assertFalse(os.path.exists(p))

    def test_mark_broken_on_job_failure(self):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)

        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.write(b"\x00" * 8)
        tmp.close()

        job = SimpleNamespace(args=(preview_file_id, tmp.name, True, False))
        preview_files_service.mark_broken_on_job_failure(
            job, None, Exception, Exception("worker killed"), None
        )

        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "broken")
        self.assertFalse(os.path.exists(tmp.name))

    def test_extract_skips_metadata_only_previews(self):
        """
        Imported-only previews have no local binary — extract functions
        must short-circuit silently (return None) so callers can no-op
        instead of crashing on FileNotFoundError.
        """
        preview_file = {
            "id": "some-uuid",
            "extension": "mp4",
            "data": {"imported_only": True},
        }
        self.assertIsNone(extract_frame_from_preview_file(preview_file, 1))
        self.assertIsNone(extract_tile_from_preview_file(preview_file))


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
        preview_files_service.update_preview_file_annotations(
            self.user_id, self.project_id, self.preview_file_id, **changes
        )
        return files_service.get_preview_file(self.preview_file_id)[
            "annotations"
        ]

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
            "zou.app.services.preview_files_service.with_preview_file_lock",
            side_effect=unavailable_lock,
        ):
            self.assertRaises(
                AnnotationLockTimeoutException,
                preview_files_service.update_preview_file_annotations,
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
            preview_files_service.normalize_preview_file_annotation_times(
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
            preview_files_service.normalize_preview_file_annotation_times(
                preview_file
            )
        )


class NormalizeAnnotationTimesTestCase(unittest.TestCase):
    """
    Snapping annotation times onto the frame grid the player draws on.
    Two times landing on the same frame become one annotation.
    """

    def normalize(self, annotations, fps=25):
        return preview_files_service.normalize_annotation_times(
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


class MissingStatusTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file(
            status="processing"
        )

    def tearDown(self):
        super().tearDown()
        self.delete_test_folder()

    def _reload_preview(self):
        return PreviewFile.get(self.preview_file.id)

    def test_set_preview_file_as_missing_persists_missing(self):
        preview_files_service.set_preview_file_as_missing(
            str(self.preview_file.id)
        )
        reloaded = self._reload_preview()
        self.assertEqual(reloaded.status.code, "missing")
        self.assertEqual(reloaded.serialize()["status"], "missing")
        self.assertEqual(reloaded.present()["status"], "missing")
        self.assertEqual(reloaded.present_minimal()["status"], "missing")


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
        entries = preview_files_service._build_annotated_frame_entries(
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


class ResetPictureFilesMetadataTestCase(ApiDBTestCase):
    """
    The command that backfills width, height and file size on picture
    previews, for rows created before those columns were filled in.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file.update({"extension": "png"})

    def store_original_picture(self):
        path = file_store.get_local_picture_path(
            "original", str(self.preview_file.id)
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open("tests/fixtures/thumbnails/th01.png", "rb") as source:
            with open(path, "wb") as target:
                target.write(source.read())
        return path

    def test_reset_picture_files_metadata(self):
        path = self.store_original_picture()
        expected = thumbnail_utils.get_dimensions(path)

        preview_files_service.reset_picture_files_metadata()

        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual((preview_file.width, preview_file.height), expected)
        self.assertEqual(preview_file.file_size, os.path.getsize(path))

    def test_a_missing_binary_does_not_stop_the_run(self):
        # The command walks the whole instance: one preview whose file never
        # made it to storage must not take the rest of the run down.
        before = PreviewFile.get(self.preview_file.id).updated_at

        preview_files_service.reset_picture_files_metadata()

        self.assertEqual(
            PreviewFile.get(self.preview_file.id).updated_at, before
        )


class ResetMovieFilesMetadataTestCase(ApiDBTestCase):
    """
    Same backfill as the picture one, reading the movie dimensions and
    duration back from the encoded file.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file()

    def test_reset_movie_files_metadata(self):
        path = file_store.get_local_movie_path(
            "previews", str(self.preview_file.id)
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open("tests/fixtures/videos/test_preview_tiles.mp4", "rb") as f:
            with open(path, "wb") as target:
                target.write(f.read())

        preview_files_service.reset_movie_files_metadata()

        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual(
            (preview_file.width, preview_file.height),
            movie.get_movie_size(path),
        )
        self.assertEqual(preview_file.file_size, os.path.getsize(path))
        self.assertGreater(preview_file.duration, 0)
