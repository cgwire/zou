import datetime
import os

from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from zou.app import db
from zou.app.blueprints.previews import resources as preview_resources
from zou.app.models.preview_file_storage_state import (
    PreviewFileStorageState,
)
from zou.app.services import files_service
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

    def test_failed_picture_stays_failed_after_recheck_delay(self):
        # A picture Zou tried and failed to generate (tile ffmpeg error,
        # ...) is not the same fact as a plain missing one: a confirmed
        # 404 on it must keep "failed", only refreshing the date so the
        # short-circuit applies again.
        states_service.record_file_state(
            self.preview_file_id,
            "pictures",
            "thumbnails",
            states_service.FAILED,
        )
        file_store.remove_picture("thumbnails", self.preview_file_id)
        self.age_states(3601)

        self.assertEqual(self.get_picture("thumbnails").status_code, 404)

        self.assertEqual(self.state("pictures", "thumbnails"), "failed")
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

    def get_movie(self):
        return self.app.get(
            f"/movies/originals/preview-files/{self.preview_file_id}.mp4",
            headers=self.base_headers,
        )

    def test_movie_skips_a_version_known_missing(self):
        # normalize=false stores the upload under `previews` only.
        self.assertEqual(self.get_movie().status_code, 200)
        self.assertEqual(self.state("movies", "previews"), "ok")
        states_service.record_file_state(
            self.preview_file_id, "movies", "previews", "missing"
        )
        with patch.object(
            preview_resources.fs,
            "get_file_path_and_file",
            wraps=fs.get_file_path_and_file,
        ) as get_file:
            # previews known missing, lowdef and source unknown: the route
            # tries lowdef then source, both absent in the local store.
            self.assertEqual(self.get_movie().status_code, 404)
        tried = [call.args[3] for call in get_file.call_args_list]
        self.assertNotIn("previews", tried)
        self.assertEqual(self.state("movies", "lowdef"), "missing")
        self.assertEqual(self.state("movies", "source"), "missing")

    def test_movie_with_every_version_known_missing_is_404_at_once(self):
        states_service.record_file_states(
            self.preview_file_id,
            {
                ("movies", "previews"): "missing",
                ("movies", "lowdef"): "missing",
                ("movies", "source"): "missing",
            },
        )
        with patch.object(
            preview_resources.fs,
            "get_file_path_and_file",
            wraps=fs.get_file_path_and_file,
        ) as get_file:
            self.assertEqual(self.get_movie().status_code, 404)
        get_file.assert_not_called()

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

    def set_processing(self):
        preview_file = files_service.get_preview_file_raw(self.preview_file_id)
        preview_file.update({"status": "processing"})
        files_service.clear_preview_file_cache(self.preview_file_id)
        # setUp's upload runs synchronously (no job queue in tests) and
        # already recorded every variant as "ok". A preview file going
        # back to "processing" (a re-upload building fresh variants) has
        # no confirmed storage yet, so the fixture is reset to match.
        for row in PreviewFileStorageState.query.filter_by(
            preview_file_id=self.preview_file_id
        ):
            db.session.delete(row)
        db.session.commit()
        states_service.clear_file_states_cache(self.preview_file_id)

    def test_a_processing_preview_answers_202_to_a_json_client(self):
        self.set_processing()
        response = self.app.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file_id}.png",
            headers={
                **self.base_headers,
                "Accept": "application/json, */*;q=0.1",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers["Retry-After"], "5")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.json["status"], "processing")
        # Nothing is missing: nothing is recorded.
        self.assertIsNone(self.state("pictures", "thumbnails"))

    def test_a_processing_preview_answers_404_to_a_browser(self):
        self.set_processing()
        response = self.app.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file_id}.png",
            headers={
                **self.base_headers,
                "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            },
        )
        self.assertEqual(response.status_code, 404)
        # A processing preview turns ready soon: this 404 must not be
        # cached by the browser past that point.
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIsNone(self.state("pictures", "thumbnails"))

    def test_a_processing_preview_answers_404_to_a_client_without_accept(
        self,
    ):
        self.set_processing()
        response = self.app.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file_id}.png",
            headers=self.base_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_a_processing_movie_answers_202_to_a_json_client(self):
        self.set_processing()
        response = self.app.get(
            f"/movies/originals/preview-files/{self.preview_file_id}.mp4",
            headers={
                **self.base_headers,
                "Accept": "application/json, */*;q=0.1",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertIsNone(self.state("movies", "previews"))

    def test_a_missing_file_still_answers_404_and_is_recorded(self):
        file_store.remove_picture("thumbnails", self.preview_file_id)
        response = self.app.get(
            f"/pictures/thumbnails/preview-files/{self.preview_file_id}.png",
            headers={
                **self.base_headers,
                "Accept": "application/json, */*;q=0.1",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.state("pictures", "thumbnails"), "missing")

    def test_the_shared_helper_answers_202_too(self):
        from zou.app import app as flask_app

        self.set_processing()
        with flask_app.test_request_context(
            headers={"Accept": "application/json, */*;q=0.1"}
        ):
            # What the shared playlist routes call, without a JWT.
            response = preview_resources.send_preview_picture_file(
                "thumbnails", self.preview_file_id
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers["Retry-After"], "5")
