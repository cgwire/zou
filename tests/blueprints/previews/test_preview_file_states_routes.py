import datetime
import os

from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from zou.app import db
from zou.app.blueprints.previews import resources as preview_resources
from zou.app.models.preview_file_storage_state import (
    PreviewFileStorageState,
)
from zou.app.services import preview_file_states_service as states_service
from zou.app.services import preview_files_service
from zou.app.stores import file_store, queue_store, redis_client
from zou.app import config
from zou.app.utils import date_helpers, fs


class PreviewFileStatesRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.movie_path = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        self.preview_file_id = self.upload_movie_preview()

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

    def get_picture(self, prefix):
        return self.app.get(
            f"/pictures/{prefix}/preview-files/{self.preview_file_id}.png",
            headers=self.base_headers,
        )

    def get_tile(self):
        return self.app.get(
            f"/movies/tiles/preview-files/{self.preview_file_id}.png",
            headers=self.base_headers,
        )

    def state(self, bucket, prefix):
        return states_service.get_state(
            states_service.get_file_states(self.preview_file_id),
            bucket,
            prefix,
        )

    def age_states(self, seconds):
        for row in PreviewFileStorageState.query.filter_by(
            preview_file_id=self.preview_file_id
        ):
            row.updated_at = date_helpers.get_utc_now_datetime() - (
                datetime.timedelta(seconds=seconds)
            )
        db.session.commit()
        states_service.clear_file_states_cache(self.preview_file_id)

    def test_upload_records_the_pictures(self):
        self.assertEqual(self.state("pictures", "thumbnails"), "ok")
        self.assertEqual(self.state("pictures", "tiles"), "ok")

    def test_missing_picture_is_recorded_then_short_circuited(self):
        file_store.remove_picture("thumbnails", self.preview_file_id)
        self.assertEqual(self.get_picture("thumbnails").status_code, 404)
        self.assertEqual(self.state("pictures", "thumbnails"), "missing")

        with patch.object(
            preview_resources.fs,
            "get_file_path_and_file",
            wraps=fs.get_file_path_and_file,
        ) as get_file:
            self.assertEqual(self.get_picture("thumbnails").status_code, 404)
            get_file.assert_not_called()

            self.age_states(3601)
            self.assertEqual(self.get_picture("thumbnails").status_code, 404)
            get_file.assert_called_once()
        # Confirmed again: the date moved, the short-circuit applies again.
        states = states_service.get_file_states(self.preview_file_id)
        self.assertTrue(
            states_service.is_known_missing(states, "pictures", "thumbnails")
        )

    def test_picture_back_in_storage_is_recorded_ok(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "previews", "missing"
        )
        self.age_states(3601)
        self.assertEqual(self.get_picture("previews").status_code, 200)
        self.assertEqual(self.state("pictures", "previews"), "ok")

    def test_transient_error_leaves_the_state(self):
        with patch.object(
            preview_resources.fs,
            "get_file_path_and_file",
            side_effect=fs.FileNotFound("503"),
        ):
            self.assertEqual(self.get_picture("previews").status_code, 404)
        self.assertEqual(self.state("pictures", "previews"), "ok")

    def test_known_missing_tile_still_queues_its_build(self):
        attempt_key = f"tile-attempt:{self.preview_file_id}"
        redis_client.get_client(config.KV_JOB_DB_INDEX).delete(attempt_key)
        file_store.remove_picture("tiles", self.preview_file_id)
        self.assertEqual(self.get_tile().status_code, 404)
        self.assertEqual(self.state("pictures", "tiles"), "missing")

        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.assertEqual(self.get_tile().status_code, 404)
        job_queue.enqueue.assert_called_once()
        redis_client.get_client(config.KV_JOB_DB_INDEX).delete(attempt_key)
