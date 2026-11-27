import datetime
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from tests.base import ApiDBTestCase
from tests.services.cases import PreviewFileTestCase
from zou.app.exceptions import (
    PreviewFileNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.services import (
    files_service,
    organisation_service,
    preview_annotations_service,
    preview_file_states_service as states_service,
    preview_files_service,
    preview_maintenance_service,
)
from zou.app.services.preview_files_service import (
    extract_frame_from_preview_file,
    extract_tile_from_preview_file,
    get_preview_file_dimensions,
    get_preview_file_fps,
)
from zou.app.stores import file_store
from zou.app.utils import fields, remote_job


def _make_temp_folder(test_case):
    """
    Create a temporary folder, removed with its content once the test ends.
    """
    folder = tempfile.mkdtemp()
    test_case.addCleanup(shutil.rmtree, folder, ignore_errors=True)
    return folder


class PreviewFileServiceTestCase(PreviewFileTestCase):
    """
    Everything but the annotations: dimensions, fps, the movie
    preparation and the broken status.
    """

    def test_save_variants_cleans_up_on_upload_failure(self):
        self.generate_fixture_preview_file()
        folder = _make_temp_folder(self)
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

    def test_update_preview_file_announces_its_status(self):
        # The clients hold back the pictures of a processing preview until
        # an update tells them it is ready.
        preview_file_id = str(
            self.generate_fixture_preview_file(status="processing").id
        )
        captured = self.capture_events("preview-file:update")

        preview_files_service.update_preview_file(
            preview_file_id, {"status": "ready"}
        )
        preview_files_service.set_preview_file_as_broken(preview_file_id)

        statuses = [event["status"] for event in captured]
        self.assertEqual(statuses, ["ready", "broken"])
        # A Choice compares equal to its code: only its type tells it apart.
        self.assertEqual([type(status) for status in statuses], [str, str])

    def test_update_preview_file_announces_a_status_that_matters(self):
        # The metadata commands refresh every ready preview: their events
        # leave the status out. The upload request still tells a preview
        # processing.
        ready_id = str(self.generate_fixture_preview_file(status="ready").id)
        processing_id = str(
            self.generate_fixture_preview_file(
                revision=2, status="processing"
            ).id
        )
        captured = self.capture_events("preview-file:update")

        preview_files_service.update_preview_file(ready_id, {"width": 1920})
        preview_files_service.update_preview_file(
            processing_id, {"original_name": "frame"}
        )

        self.assertEqual(
            [event.get("status") for event in captured], [None, "processing"]
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
        fps = get_preview_file_fps({"fps": "24,00"})
        self.assertEqual(fps, "24.000")

    def test_the_fps_of_the_entity_overrides_the_project_one(self):
        project = {"fps": "24"}
        # A number, as the entity data can hold one (cgwire/zou#901).
        self.assertEqual(
            get_preview_file_fps(project, {"data": {"fps": 30}}), "30.000"
        )
        self.assertEqual(
            get_preview_file_fps(project, {"data": {"fps": "12,5"}}),
            "12.500",
        )
        # An emptied entity field falls back on the project.
        for data in ({"fps": ""}, {"fps": None}, None):
            with self.subTest(data=data):
                self.assertEqual(
                    get_preview_file_fps(project, {"data": data}), "24.000"
                )

    def test_encoding_parameters_read_the_task_type_link(self):
        preview_file = self.generate_fixture_preview_file()
        self.project.update({"hd_bitrate_compression": 20})
        ProjectTaskTypeLink.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            ld_bitrate_compression=4,
        )
        fps, width, height, bitrates = (
            preview_files_service._get_encoding_parameters(preview_file.id)
        )
        self.assertEqual(bitrates, (20, 4))

    def test_encoding_parameters_of_a_deleted_preview_file(self):
        # Still missing after the retry: deleted while the job waited. It
        # must stay a PreviewFileNotFoundException, which
        # prepare_and_store_movie logs as a warning, not an error.
        with patch.object(preview_files_service.time, "sleep"):
            self.assertRaises(
                PreviewFileNotFoundException,
                preview_files_service._get_encoding_parameters,
                "5464d4b6-f419-4c76-8734-c6c489441177",
            )

    def test_get_project_from_preview_file(self):
        preview_file = self.generate_fixture_preview_file()
        project = preview_files_service.get_project_from_preview_file(
            preview_file.id
        )
        self.assertEqual(project["id"], self.project_id)

    def test_get_last_preview_file_for_task(self):
        self.assertIsNone(
            preview_files_service.get_last_preview_file_for_task(self.task_id)
        )

        self.generate_fixture_preview_file()
        self.generate_fixture_preview_file(revision=2)
        preview_file = preview_files_service.get_last_preview_file_for_task(
            self.task_id
        )
        self.assertEqual(preview_file["revision"], 2)

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
        uploaded_path = self._write_temp_movie()
        norm_path = self._write_temp_movie(size=512)
        norm_low_path = self._write_temp_movie(size=512)

        mock_normalize.return_value = (norm_path, norm_low_path, None)
        mock_gen_thumbnail.return_value = norm_path
        mock_gen_tile.return_value = norm_path

        original_width = 720
        original_height = 1280
        original_duration = 42.5
        normalized_width = 1920
        normalized_height = 1080

        with patch(
            "zou.app.services.preview_files_service.movie.get_movie_size",
            side_effect=lambda path, **kwargs: (
                (original_width, original_height)
                if path == uploaded_path
                else (normalized_width, normalized_height)
            ),
        ), patch(
            "zou.app.services.preview_files_service.movie.get_movie_duration",
            side_effect=lambda path=None, **kwargs: (
                original_duration if path == uploaded_path else 40.0
            ),
        ):
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

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_a_failed_original_metadata_capture_does_not_stop_the_movie(
        self,
        mock_add_movie,
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
        reads = []

        def size_failing_once(path, **kwargs):
            # The first read is the capture of the original metadata.
            reads.append(path)
            if len(reads) == 1:
                raise RuntimeError("ffprobe crashed")
            return 1920, 1080

        mock_size.side_effect = size_failing_once
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

        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")
        self.assertEqual(persisted["width"], 1920)
        self.assertNotIn("original_width", persisted["data"] or {})

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
    def test_prepare_and_store_movie_skip_full_keeps_a_single_copy(
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
        """
        The uploaded movie already went to the storage as the source, and
        the movie routes fall back on it: a copy under `previews` would be
        the same bytes twice.
        """
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
                add_source_to_file_store=True,
            )

        mock_normalize.assert_not_called()
        self.assertEqual(
            [
                (call.args[0], call.args[2])
                for call in mock_add_movie.mock_calls
            ],
            [("source", uploaded_path)],
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

    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    @patch(
        "zou.app.services.preview_files_service"
        ".is_remote_normalization_enabled"
    )
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_prepare_and_store_movie_remote_job_runs_without_normalization(
        self,
        mock_add_movie,
        mock_is_remote,
        mock_run_remote,
        mock_size,
        mock_duration,
        mock_gen_thumbnail,
    ):
        """
        The remote job builds the thumbnails and the tile, so it has to be
        dispatched even when nothing is normalized.
        """
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        mock_is_remote.return_value = True
        mock_run_remote.return_value = True
        mock_size.return_value = (1920, 1080)
        mock_duration.return_value = 10.0

        with patch.object(
            preview_files_service.config, "SKIP_NORMALIZATION_FULL", True
        ):
            preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )

        self.assertTrue(mock_run_remote.call_args.kwargs["skip_normalization"])
        # No movie stored: the source uploaded for the job is the only one,
        # and the thumbnails are the remote job's business.
        mock_add_movie.assert_not_called()
        mock_gen_thumbnail.assert_not_called()
        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")
        self.assertEqual(persisted["width"], 1920)
        self.assertEqual(persisted["file_size"], 1024)

    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch("zou.app.services.preview_files_service.fs.get_file_path_and_file")
    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    @patch(
        "zou.app.services.preview_files_service"
        ".is_remote_normalization_enabled"
    )
    def test_prepare_and_store_movie_remote_job_records_what_it_stored(
        self,
        mock_is_remote,
        mock_run_remote,
        mock_get_file,
        mock_size,
        mock_duration,
    ):
        """
        A runner that predates skip_high_def uploads both encoded versions
        whatever the flag: the record comes from the storage, not from
        the flags.
        """
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        mock_is_remote.return_value = True
        mock_run_remote.return_value = True
        mock_get_file.return_value = self._write_temp_movie()
        mock_size.return_value = (1280, 720)
        mock_duration.return_value = 10.0

        with patch.object(
            preview_files_service.config, "SKIP_NORMALIZATION_HIGHDEF", True
        ), patch.object(
            preview_files_service.file_store,
            "exists_movie",
            side_effect=lambda prefix, _id: prefix in ("previews", "lowdef"),
        ):
            preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )

        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")
        self.assertEqual(
            persisted["data"][files_service.MOVIE_PREFIXES_KEY],
            ["previews", "lowdef"],
        )
        states = states_service.get_file_states(preview_file_id)
        self.assertEqual(states["movies/previews"]["state"], "ok")
        # Not produced is not confirmed missing: nothing recorded.
        self.assertNotIn("movies/source", states)
        # The runner was supposed to write the pictures: none are there.
        self.assertEqual(states["pictures/tiles"]["state"], "failed")

    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    @patch(
        "zou.app.services.preview_files_service"
        ".is_remote_normalization_enabled"
    )
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_a_handed_over_normalization_keeps_its_upload(
        self, mock_add_movie, mock_is_remote, mock_run_remote
    ):
        """
        When the worker stops while Nomad encodes the movie, the next
        worker resumes the job: the upload stays for it and the preview
        file stays "processing".
        """
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        mock_is_remote.return_value = True
        mock_run_remote.side_effect = remote_job.NomadJobHandedOver()

        with patch.object(
            preview_files_service, "_get_encoding_parameters"
        ) as encoding_parameters, patch.object(
            preview_files_service, "_record_original_metadata"
        ), patch.object(
            preview_files_service, "set_preview_file_as_broken"
        ) as set_broken:
            encoding_parameters.return_value = (25.0, 1920, 1080, (28, 6))
            self.assertRaises(
                remote_job.NomadJobHandedOver,
                preview_files_service.prepare_and_store_movie,
                preview_file_id,
                uploaded_path,
            )

        self.assertTrue(os.path.exists(uploaded_path))
        set_broken.assert_not_called()

    @patch("zou.app.services.preview_files_service.movie.get_movie_duration")
    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    @patch(
        "zou.app.services.preview_files_service"
        ".is_remote_normalization_enabled"
    )
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_a_resumed_normalization_does_not_store_the_source_again(
        self,
        mock_add_movie,
        mock_is_remote,
        mock_run_remote,
        mock_size,
        mock_duration,
    ):
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        uploaded_path = self._write_temp_movie()
        mock_is_remote.return_value = True
        mock_run_remote.return_value = True
        mock_size.return_value = (1920, 1080)
        mock_duration.return_value = 10.0

        with patch.object(
            preview_files_service.config, "SKIP_NORMALIZATION_FULL", True
        ), patch.object(remote_job, "is_resumed", return_value=True):
            preview_files_service.prepare_and_store_movie(
                preview_file_id, uploaded_path
            )

        mock_add_movie.assert_not_called()
        persisted = files_service.get_preview_file(preview_file_id)
        self.assertEqual(persisted["status"], "ready")

    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    def test_remote_encode_does_not_read_a_stale_cache_entry(
        self, mock_run_remote
    ):
        """
        The encoded movie is fetched back through the movie routes' cache
        path. A copy of a previous encoding sitting there (the movie was
        played on this host, then renormalized) must not short-circuit
        the download: the metadata would describe the old file.
        """
        from zou.app import config
        from zou.app.utils import fs

        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        mock_run_remote.return_value = True
        cache_path = fs.get_cache_file_path(
            config, "previews", preview_file_id, "mp4"
        )
        with open(cache_path, "wb") as cache_file:
            cache_file.write(b"old encoding")
        self.addCleanup(fs.rm_file, cache_path)

        with patch.object(config, "FS_BACKEND", "s3"), patch.object(
            file_store,
            "open_movie",
            side_effect=lambda prefix, _id: iter([b"new encoding"]),
        ):
            temp_files = []
            movie_path = preview_files_service._encode_on_remote_worker(
                preview_file_id,
                "/tmp/upload.mp4",
                25,
                0,
                0,
                (28, 6),
                True,
                False,
                temp_files,
            )

        with open(movie_path, "rb") as movie_file:
            self.assertEqual(movie_file.read(), b"new encoding")
        # The worker may not be a web host: the copy goes with the other
        # temporary files instead of piling up in its TMP_DIR.
        self.assertEqual(temp_files, [movie_path])

    @patch("zou.app.services.preview_files_service._process_movie")
    def test_prepare_and_store_movie_lets_the_job_timeout_through(
        self, mock_process
    ):
        """
        rq raises its timeout inside the job: swallowed, the job counts as
        successful, never reaches the failed registry, and the failure
        callback that marks the preview file as broken never runs.
        """
        from rq.timeouts import JobTimeoutException

        preview_file = self.generate_fixture_preview_file(status="processing")
        uploaded_path = self._write_temp_movie()
        mock_process.side_effect = JobTimeoutException()

        with self.assertRaises(JobTimeoutException):
            preview_files_service.prepare_and_store_movie(
                str(preview_file.id), uploaded_path, normalize=True
            )
        self.assertFalse(os.path.exists(uploaded_path))

    @patch(
        "zou.app.services.preview_files_service._run_remote_normalize_movie"
    )
    def test_remote_encode_keeps_the_stored_movie_on_a_local_backend(
        self, mock_run_remote
    ):
        """
        On a local backend the path fetched back is the stored movie
        itself, not a copy: it must not go with the temporary files.
        """
        preview_file = self.generate_fixture_preview_file(status="processing")
        preview_file_id = str(preview_file.id)
        mock_run_remote.return_value = True
        stored_path = file_store.get_local_movie_path(
            "previews", preview_file_id
        )
        os.makedirs(os.path.dirname(stored_path), exist_ok=True)
        with open(stored_path, "wb") as stored:
            stored.write(b"encoded")

        temp_files = []
        movie_path = preview_files_service._encode_on_remote_worker(
            preview_file_id,
            "/tmp/upload.mp4",
            25,
            0,
            0,
            (28, 6),
            True,
            False,
            temp_files,
        )

        self.assertEqual(movie_path, stored_path)
        self.assertEqual(temp_files, [])

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

    def test_locate_stored_movie_tries_every_version(self):
        """
        SKIP_NORMALIZATION_HIGHDEF keeps the low def movie only, and the
        source only option keeps the upload: a reader pinned on the
        "previews" version fails on those instances.
        """
        self.generate_fixture_preview_file()
        preview_file_id = str(self.preview_file.id)
        preview_file = {"id": preview_file_id, "extension": "mp4", "data": {}}
        movie_fixture = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        with self.assertRaises(PreviewFileNotFoundException):
            preview_files_service.locate_stored_movie(preview_file)

        file_store.add_movie("lowdef", preview_file_id, movie_fixture)
        try:
            path = preview_files_service.locate_stored_movie(preview_file)
            self.assertTrue(os.path.exists(path))
            self.assertIn("lowdef", path)
        finally:
            file_store.remove_movie("lowdef", preview_file_id, force=True)

    def test_locate_stored_movie_keeps_a_transient_failure(self):
        # Only an absence the store confirmed sends the reader to the next
        # version: a hiccup on the high def movie must not hand out the
        # low def one, whose size would be recorded as the preview's.
        self.generate_fixture_preview_file()
        preview_file = {
            "id": str(self.preview_file.id),
            "extension": "mp4",
            "data": {},
        }
        with patch.object(
            preview_files_service.fs,
            "get_file_path_and_file",
            side_effect=preview_files_service.fs.FileNotFound("previews-x"),
        ) as get_file:
            with self.assertRaises(preview_files_service.fs.FileNotFound):
                preview_files_service.locate_stored_movie(preview_file)
        self.assertEqual(get_file.call_count, 1)

    def test_a_storage_outage_is_not_a_missing_picture(self):
        self.generate_fixture_preview_file()
        preview_file = {"id": str(self.preview_file.id), "extension": "png"}
        with patch.object(
            preview_files_service.fs,
            "get_file_path_and_file",
            side_effect=preview_files_service.fs.ConfirmedFileNotFound("x"),
        ):
            self.assertIsNone(
                preview_annotations_service._copy_picture_preview_to_temp_png(
                    preview_file
                )
            )
        with patch.object(
            preview_files_service.fs,
            "get_file_path_and_file",
            side_effect=RuntimeError("storage down"),
        ):
            with self.assertRaises(RuntimeError):
                preview_annotations_service._copy_picture_preview_to_temp_png(
                    preview_file
                )

    def test_update_preview_file_does_not_retry_a_missing_row(self):
        # The retries are for transient database errors on job workers; a
        # deleted preview used to cost six seconds of sleep before raising.
        with patch.object(preview_files_service.time, "sleep") as sleep:
            with self.assertRaises(PreviewFileNotFoundException):
                preview_files_service.update_preview_file(
                    fields.gen_uuid(), {"status": "broken"}
                )
        sleep.assert_not_called()

    def test_update_preview_file_retries_a_transient_db_error(self):
        preview_file_id = str(
            self.generate_fixture_preview_file(status="processing").id
        )
        get_raw = files_service.get_preview_file_raw
        calls = []

        def fail_twice(preview_file_id):
            calls.append(preview_file_id)
            if len(calls) < 3:
                raise OperationalError("SELECT", {}, Exception("db lost"))
            return get_raw(preview_file_id)

        with patch.object(
            files_service, "get_preview_file_raw", side_effect=fail_twice
        ), patch.object(preview_files_service.time, "sleep") as sleep:
            preview_files_service.update_preview_file(
                preview_file_id, {"status": "ready"}
            )
        self.assertEqual([c.args for c in sleep.call_args_list], [(1,), (5,)])
        self.assertEqual(
            files_service.get_preview_file(preview_file_id)["status"], "ready"
        )

    @patch("zou.app.services.preview_files_service.movie.get_movie_size")
    def test_prepare_and_store_movie_of_a_deleted_preview_file(
        self, mock_size
    ):
        mock_size.return_value = (1920, 1080)
        uploaded_path = self._write_temp_movie()
        preview_file_id = fields.gen_uuid()
        with patch.object(preview_files_service.time, "sleep"):
            result = preview_files_service.prepare_and_store_movie(
                preview_file_id,
                uploaded_path,
                normalize=True,
                add_source_to_file_store=False,
            )
        self.assertEqual(result, {"id": preview_file_id, "status": "broken"})
        self.assertFalse(os.path.exists(uploaded_path))

    @patch("zou.app.services.preview_files_service.movie.normalize_movie")
    @patch("zou.app.services.preview_files_service.file_store.add_movie")
    def test_a_local_encode_error_marks_the_preview_broken(
        self, mock_add_movie, mock_normalize
    ):
        preview_file_id = str(
            self.generate_fixture_preview_file(status="processing").id
        )
        uploaded_path = self._write_temp_movie()
        low_def_path = self._write_temp_movie()
        mock_normalize.return_value = (None, low_def_path, "ffmpeg failed")

        result = preview_files_service.prepare_and_store_movie(
            preview_file_id,
            uploaded_path,
            normalize=True,
            add_source_to_file_store=False,
        )

        self.assertEqual(result["status"], "broken")
        mock_add_movie.assert_not_called()
        for path in (uploaded_path, low_def_path):
            self.assertFalse(os.path.exists(path))

    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_remote_normalize_sends_the_encoding_parameters(
        self, mock_run_job
    ):
        mock_run_job.return_value = True
        with patch.object(
            preview_files_service.config_store,
            "get_nomad_normalize_job",
            return_value="zou-normalize",
        ):
            preview_files_service._run_remote_normalize_movie(
                None,
                "preview-id",
                "24.000",
                1920,
                1080,
                bitrates=(28, 6),
                skip_high_def=True,
            )
            preview_files_service._run_remote_normalize_movie(
                None, "preview-id", "24.000", None, 1080
            )

        nomad_job, params = mock_run_job.call_args_list[0].args[2:]
        self.assertEqual(nomad_job, "zou-normalize")
        self.assertEqual(
            {
                key: params[key]
                for key in params
                if key not in ("preset", "vbv_bufsize_factor")
            },
            {
                "version": str(preview_files_service.REMOTE_NORMALIZE_VERSION),
                "preview_file_id": "preview-id",
                "width": 1920,
                "height": 1080,
                "fps": "24.000",
                "skip_high_def": True,
                "skip_normalization": False,
                "highdef_bitrate": 28,
                "lowdef_bitrate": 6,
            },
        )
        # Without bitrates, the runner keeps its own defaults.
        params = mock_run_job.call_args_list[1].args[3]
        self.assertNotIn("highdef_bitrate", params)
        self.assertNotIn("lowdef_bitrate", params)

    @patch(
        "zou.app.services.preview_files_service.movie.extract_frame_from_movie"
    )
    @patch("zou.app.services.preview_files_service.fs.get_file_path_and_file")
    def test_extract_frame_reads_the_fps_of_the_entity(
        self, mock_get_file, mock_extract
    ):
        preview_file = self.generate_fixture_preview_file().serialize()
        self.asset.update({"data": {"fps": "12"}})
        mock_get_file.return_value = "/stored/movie.mp4"
        mock_extract.return_value = "/tmp/frame.png"

        path = extract_frame_from_preview_file(preview_file, 7)

        self.assertEqual(path, "/tmp/frame.png")
        mock_extract.assert_called_once_with("/stored/movie.mp4", 7, "12.000")

    def test_get_running_preview_files_pages_with_a_cursor(self):
        older = self.generate_fixture_preview_file(status="processing")
        older.update({"created_at": datetime.datetime(2020, 1, 1)})
        newer = self.generate_fixture_preview_file(revision=2, status="broken")
        self.generate_fixture_preview_file(revision=3, status="ready")

        page = preview_files_service.get_running_preview_files(limit=1)
        self.assertEqual([p["id"] for p in page], [str(newer.id)])
        page = preview_files_service.get_running_preview_files(
            cursor_preview_file_id=str(newer.id)
        )
        self.assertEqual([p["id"] for p in page], [str(older.id)])
        with self.assertRaises(WrongParameterException):
            preview_files_service.get_running_preview_files(
                cursor_preview_file_id=fields.gen_uuid()
            )

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


class MissingStatusTestCase(PreviewFileTestCase):
    def test_set_preview_file_as_missing_persists_missing(self):
        preview_file_id = str(
            self.generate_fixture_preview_file(status="processing").id
        )

        preview_files_service.set_preview_file_as_missing(preview_file_id)

        self.assertEqual(
            files_service.get_preview_file(preview_file_id)["status"],
            "missing",
        )


class PreviewFileWritesRecordStatesTestCase(PreviewFileTestCase):
    def setUp(self):
        super().setUp()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file_id = str(self.preview_file.id)

    def states(self):
        return {
            key: value["state"]
            for key, value in states_service.get_file_states(
                self.preview_file_id
            ).items()
        }

    def test_save_variants_records_the_pictures(self):
        picture_path = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        tmp_path = os.path.join(_make_temp_folder(self), "original.png")
        shutil.copyfile(picture_path, tmp_path)
        preview_files_service.save_variants(self.preview_file_id, tmp_path)
        states = self.states()
        for prefix in ["original", "thumbnails", "thumbnails-square"]:
            self.assertEqual(states[f"pictures/{prefix}"], "ok")

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    def test_failed_tile_is_recorded(self, mock_tile):
        mock_tile.side_effect = RuntimeError("ffmpeg")
        preview_files_service.generate_tiles(
            file_store, self.preview_file, "/tmp/movie.mp4", 1, 1, force=True
        )
        self.assertEqual(self.states()["pictures/tiles"], "failed")

    @patch("zou.app.services.preview_files_service.file_store.add_picture")
    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    def test_built_tile_is_recorded(self, mock_tile, mock_add_picture):
        tile_path = os.path.join(_make_temp_folder(self), "tile.png")
        open(tile_path, "wb").close()
        mock_tile.return_value = tile_path
        preview_files_service.generate_tiles(
            file_store, self.preview_file, "/tmp/movie.mp4", 1, 1, force=True
        )
        self.assertEqual(self.states()["pictures/tiles"], "ok")

    @patch("zou.app.services.preview_files_service.os.remove")
    @patch("zou.app.services.preview_files_service.file_store.add_picture")
    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    def test_tile_stays_ok_when_removing_the_local_copy_fails(
        self, mock_tile, mock_add_picture, mock_remove
    ):
        # The tile already made it to the store: a failure removing the
        # local temp copy afterwards must not turn the recorded state
        # back to failed.
        tile_path = os.path.join(_make_temp_folder(self), "tile.png")
        open(tile_path, "wb").close()
        mock_tile.return_value = tile_path
        mock_remove.side_effect = OSError("permission denied")
        preview_files_service.generate_tiles(
            file_store, self.preview_file, "/tmp/movie.mp4", 1, 1, force=True
        )
        self.assertEqual(self.states()["pictures/tiles"], "ok")

    @patch("zou.app.services.preview_files_service.os.remove")
    @patch("zou.app.services.preview_files_service.file_store.add_picture")
    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    def test_build_thumbnails_and_tile_stays_ok_when_remove_fails(
        self,
        mock_generate_thumbnail,
        mock_turn_into_thumbnail,
        mock_save_variants,
        mock_generate_tile,
        mock_add_picture,
        mock_remove,
    ):
        thumbnail_path = os.path.join(_make_temp_folder(self), "thumb.png")
        open(thumbnail_path, "wb").close()
        mock_generate_thumbnail.return_value = thumbnail_path
        tile_path = os.path.join(_make_temp_folder(self), "tile.png")
        open(tile_path, "wb").close()
        mock_generate_tile.return_value = tile_path

        def fail_only_on_tile(path):
            if path == tile_path:
                raise OSError("permission denied")

        mock_remove.side_effect = fail_only_on_tile

        preview_files_service._build_thumbnails_and_tile(
            self.preview_file_id, "/tmp/movie.mp4", (100, 100), []
        )
        self.assertEqual(self.states()["pictures/tiles"], "ok")

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.save_variants")
    @patch(
        "zou.app.services.preview_files_service.thumbnail_utils"
        ".turn_into_thumbnail"
    )
    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    def test_build_thumbnails_and_tile_records_a_failed_tile(
        self,
        mock_generate_thumbnail,
        mock_turn_into_thumbnail,
        mock_save_variants,
        mock_generate_tile,
    ):
        # A missing tile is not fatal: the preview still becomes ready.
        mock_generate_thumbnail.return_value = os.path.join(
            _make_temp_folder(self), "thumb.png"
        )
        mock_generate_tile.side_effect = RuntimeError("ffmpeg")
        preview_files_service._build_thumbnails_and_tile(
            self.preview_file_id, "/tmp/movie.mp4", (100, 100), []
        )
        self.assertEqual(self.states()["pictures/tiles"], "failed")

    @patch("zou.app.services.preview_files_service.movie.generate_thumbnail")
    def test_generate_thumbnails_of_a_movie_keeps_no_original(
        self, mock_generate_thumbnail
    ):
        picture_path = os.path.join(_make_temp_folder(self), "frame.png")
        shutil.copyfile(
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            picture_path,
        )
        mock_generate_thumbnail.return_value = picture_path
        preview_files_service.generate_thumbnails(
            self.preview_file, "/tmp/movie.mp4", 1, 1
        )
        mock_generate_thumbnail.assert_called_once_with("/tmp/movie.mp4")
        states = self.states()
        self.assertEqual(states["pictures/thumbnails"], "ok")
        # The frame of a movie is not an original picture.
        self.assertNotIn("pictures/original", states)

        # A failure is logged: the maintenance loop goes on.
        mock_generate_thumbnail.side_effect = RuntimeError("ffmpeg")
        preview_files_service.generate_thumbnails(
            self.preview_file, "/tmp/movie.mp4", 1, 1
        )

    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_remote_tile_job_without_tile_is_failed(self, mock_run_job):
        mock_run_job.return_value = True
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE_REMOTE", True
        ), patch.object(
            preview_files_service.config_store,
            "get_nomad_tile_job",
            return_value="zou-tile-go",
        ), patch.object(
            file_store, "exists_confirmed", return_value=False
        ):
            preview_maintenance_service.generate_missing_tile(
                self.preview_file_id
            )
        self.assertEqual(self.states()["pictures/tiles"], "failed")

    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_remote_tile_job_dispatch_error_leaves_state_unchanged(
        self, mock_run_job
    ):
        # A Nomad dispatch error or timeout is transient: it must not be
        # recorded as a failed tile.
        mock_run_job.side_effect = RuntimeError("Nomad unreachable")
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE_REMOTE", True
        ), patch.object(
            preview_files_service.config_store,
            "get_nomad_tile_job",
            return_value="zou-tile-go",
        ):
            with self.assertRaises(RuntimeError):
                preview_maintenance_service.generate_missing_tile(
                    self.preview_file_id
                )
        self.assertNotIn("pictures/tiles", self.states())


class PreviewFileNameTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.asset_task = self.generate_fixture_task().serialize()
        self.shot_task = self.generate_fixture_shot_task().serialize()

    def a_sequence_under_no_episode(self, name="S02"):
        """
        generate_fixture_sequence reads episode_id=None as "the usual
        episode", so a sequence with nothing above it is built here.
        """
        return Entity.create(
            name=name,
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )

    def test_get_preview_file_name(self):
        preview_file = files_service.create_preview_file(
            "main", 3, self.shot_task["id"], self.user["id"], source="webgui"
        )
        name = preview_files_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_e01_s01_p01_animation_v3.mp4")

        preview_file = files_service.create_preview_file(
            "main", 3, self.asset_task["id"], self.user["id"], source="webgui"
        )
        name = preview_files_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_props_tree_shaders_v3.mp4")

        preview_file = files_service.create_preview_file(
            "main",
            4,
            self.asset_task["id"],
            self.user["id"],
            source="webgui",
            position=5,
        )
        name = preview_files_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "cosmos_landromat_props_tree_shaders_v4-5.mp4")

    def test_get_preview_file_name_uses_the_original_name(self):
        preview_file = files_service.create_preview_file(
            "main", 3, self.shot_task["id"], self.user["id"], source="webgui"
        )
        preview_files_service.update_preview_file(
            preview_file["id"], {"original_name": "my_render"}
        )
        self.addCleanup(organisation_service.clear_organisation_cache)
        organisation = organisation_service.get_organisation()
        organisation_service.update_organisation(
            organisation["id"], {"use_original_file_name": True}
        )
        name = preview_files_service.get_preview_file_name(preview_file["id"])
        self.assertEqual(name, "my_render.mp4")
