import datetime
from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.preview_file_storage_state import (
    PreviewFileStorageState,
)
from zou.app.services import preview_file_states_service as states_service
from zou.app.stores import file_store
from zou.app.utils import date_helpers


class PreviewFileStatesServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file_id = str(self.preview_file.id)

    def rows(self):
        return {
            (row.bucket, row.prefix): row.state.code
            for row in PreviewFileStorageState.query.filter_by(
                preview_file_id=self.preview_file_id
            )
        }

    def age_state(self, bucket, prefix, seconds):
        row = PreviewFileStorageState.query.filter_by(
            preview_file_id=self.preview_file_id,
            bucket=bucket,
            prefix=prefix,
        ).one()
        row.updated_at = date_helpers.get_utc_now_datetime() - (
            datetime.timedelta(seconds=seconds)
        )
        db.session.commit()
        states_service.clear_file_states_cache(self.preview_file_id)

    def test_expected_files_per_kind(self):
        self.assertIn(
            ("pictures", "tiles"), states_service.get_expected_files("mp4")
        )
        self.assertIn(
            ("movies", "lowdef"), states_service.get_expected_files("mp4")
        )
        self.assertNotIn(
            ("pictures", "tiles"), states_service.get_expected_files("png")
        )
        self.assertEqual(
            states_service.get_expected_files("pdf"), [("files", "previews")]
        )

    def test_record_and_read_states(self):
        self.assertTrue(
            states_service.record_file_states(
                self.preview_file_id,
                {
                    ("pictures", "tiles"): states_service.MISSING,
                    ("movies", "lowdef"): states_service.OK,
                },
            )
        )
        self.assertEqual(
            self.rows(),
            {("pictures", "tiles"): "missing", ("movies", "lowdef"): "ok"},
        )
        states = states_service.get_file_states(self.preview_file_id)
        self.assertEqual(states["pictures/tiles"]["state"], "missing")
        self.assertEqual(
            states_service.get_state(states, "movies", "lowdef"), "ok"
        )

    def test_unchanged_state_is_not_written(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.OK
        )
        self.assertFalse(
            states_service.record_file_state(
                self.preview_file_id, "pictures", "tiles", states_service.OK
            )
        )

    def test_state_change_updates_the_row(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.OK
        )
        self.assertEqual(self.rows(), {("pictures", "tiles"): "ok"})
        self.assertEqual(PreviewFileStorageState.query.count(), 1)

    def test_known_missing_expires(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        states = states_service.get_file_states(self.preview_file_id)
        self.assertTrue(
            states_service.is_known_missing(states, "pictures", "tiles")
        )
        self.assertFalse(
            states_service.is_known_missing(states, "pictures", "previews")
        )
        self.age_state("pictures", "tiles", 3601)
        states = states_service.get_file_states(self.preview_file_id)
        self.assertFalse(
            states_service.is_known_missing(states, "pictures", "tiles")
        )

    def test_failed_counts_as_known_missing(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.FAILED
        )
        states = states_service.get_file_states(self.preview_file_id)
        self.assertTrue(
            states_service.is_known_missing(states, "pictures", "tiles")
        )

    def test_refresh_moves_the_date_of_an_unchanged_state(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        self.age_state("pictures", "tiles", 3601)
        self.assertTrue(
            states_service.record_file_state(
                self.preview_file_id,
                "pictures",
                "tiles",
                states_service.MISSING,
                refresh=True,
            )
        )
        states = states_service.get_file_states(self.preview_file_id)
        self.assertTrue(
            states_service.is_known_missing(states, "pictures", "tiles")
        )

    def test_states_go_with_the_preview_file(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.OK
        )
        self.preview_file.delete()
        self.assertEqual(PreviewFileStorageState.query.count(), 0)

    def test_write_error_is_swallowed(self):
        self.assertFalse(
            states_service.record_file_state(
                "4b7a1c3e-0000-4000-8000-000000000000",
                "pictures",
                "tiles",
                states_service.OK,
            )
        )


class ProbeFileStatesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file_id = str(self.generate_fixture_preview_file().id)

    def test_probe_asks_the_storage_for_each_expected_file(self):
        def exists_confirmed(bucket, prefix, _id):
            if bucket == "movies":
                return True
            return prefix != "tiles"

        with patch.object(file_store, "exists_confirmed", exists_confirmed):
            states = states_service.probe_file_states(
                self.preview_file_id, "mp4"
            )
        self.assertEqual(states[("pictures", "tiles")], "missing")
        self.assertEqual(states[("movies", "lowdef")], "ok")
        self.assertEqual(len(states), 8)

    def test_probe_leaves_out_a_file_whose_check_failed(self):
        with patch.object(
            file_store, "exists_confirmed", side_effect=RuntimeError("503")
        ):
            states = states_service.probe_file_states(
                self.preview_file_id, "pdf"
            )
        self.assertEqual(states, {})
