import os
from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from tests.base import ApiDBTestCase

from zou.app.models.preview_file import PreviewFile
from zou.app.services import (
    files_service,
    preview_files_service,
    preview_maintenance_service,
    preview_file_states_service as states_service,
)
from zou.app import config
from zou.app.stores import file_store, queue_store, redis_client
from zou.app.utils import thumbnail as thumbnail_utils
from zou.utils import movie
from tests.services.cases import PreviewFileTestCase, SpyProgress


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

        preview_maintenance_service.reset_picture_files_metadata()

        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual((preview_file.width, preview_file.height), expected)
        self.assertEqual(preview_file.file_size, os.path.getsize(path))

    def test_a_missing_binary_does_not_stop_the_run(self):
        # The command walks the whole instance: one preview whose file never
        # made it to storage must not take the rest of the run down.
        before = PreviewFile.get(self.preview_file.id).updated_at

        preview_maintenance_service.reset_picture_files_metadata()

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

        preview_maintenance_service.reset_movie_files_metadata()

        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual(
            (preview_file.width, preview_file.height),
            movie.get_movie_size(path),
        )
        self.assertEqual(preview_file.file_size, os.path.getsize(path))
        self.assertGreater(preview_file.duration, 0)


class MissingTileTestCase(PreviewFileTestCase):
    """
    Building the tile sheet of a ready movie that has none, after a tile
    404: on Nomad when a tile job is configured, locally otherwise, one
    attempt per hour and one local build at a time.
    """

    def setUp(self):
        super().setUp()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file_id = str(self.preview_file.id)
        self.redis = redis_client.get_client(config.KV_JOB_DB_INDEX)
        self.redis.delete(
            preview_maintenance_service._tile_attempt_key(
                self.preview_file_id
            ),
            preview_maintenance_service.LOCAL_TILE_BUILD_LOCK_KEY,
        )

    def tearDown(self):
        self.redis.delete(
            preview_maintenance_service._tile_attempt_key(
                self.preview_file_id
            ),
            preview_maintenance_service.LOCAL_TILE_BUILD_LOCK_KEY,
        )
        super().tearDown()

    @contextmanager
    def job_queue(self):
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            yield job_queue

    @contextmanager
    def remote_tile_job(self, job_name="zou-tile-go"):
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE_REMOTE", True
        ), patch.object(
            preview_files_service.config_store,
            "get_nomad_tile_job",
            return_value=job_name,
        ):
            yield

    def test_tile_attempt_is_remembered_in_redis(self):
        """
        The attempt mark outlives TMP_DIR, which a reboot empties: it is
        kept in Redis, with the retry delay as its lifetime.
        """
        with self.job_queue() as job_queue:
            self.assertTrue(
                preview_maintenance_service.generate_tile_later(
                    self.preview_file_id
                )
            )
            # What a reboot does to a mark kept in TMP_DIR.
            mark_path = os.path.join(
                config.TMP_DIR, f"tile-{self.preview_file_id}.mark"
            )
            if os.path.exists(mark_path):
                os.remove(mark_path)
            self.assertFalse(
                preview_maintenance_service.generate_tile_later(
                    self.preview_file_id
                )
            )
        self.assertEqual(job_queue.enqueue.call_count, 1)
        ttl = self.redis.ttl(
            preview_maintenance_service._tile_attempt_key(self.preview_file_id)
        )
        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, preview_maintenance_service.TILE_RETRY_DELAY)

    @patch("zou.app.services.preview_files_service.movie.generate_tile")
    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_missing_tile_is_built_on_nomad(self, mock_run_job, mock_tile):
        """
        With a Nomad tile job configured, the web host runs no ffmpeg: the
        runner gets the preview id and the prefixes recorded for it.
        """
        preview_file = files_service.get_preview_file_raw(self.preview_file_id)
        preview_file.update(
            {"data": {files_service.MOVIE_PREFIXES_KEY: ["lowdef"]}}
        )
        files_service.clear_preview_file_cache(self.preview_file_id)

        with self.remote_tile_job():
            self.assertTrue(
                preview_maintenance_service.generate_missing_tile(
                    self.preview_file_id
                )
            )

        mock_tile.assert_not_called()
        mock_run_job.assert_called_once()
        _app, _config, job_name, params = mock_run_job.call_args.args
        self.assertEqual(job_name, "zou-tile-go")
        self.assertEqual(
            params,
            {
                "version": str(
                    preview_maintenance_service.REMOTE_TILE_VERSION
                ),
                "preview_file_id": self.preview_file_id,
                "movie_prefixes": ["lowdef"],
            },
        )

    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_missing_tile_is_built_locally_without_a_tile_job(
        self, mock_run_job
    ):
        """
        Remote normalization alone does not send tiles to Nomad: without a
        tile job name, the build stays local.
        """
        with self.remote_tile_job(job_name=""), patch.object(
            preview_files_service, "retrieve_preview_file", return_value=None
        ):
            preview_maintenance_service.generate_missing_tile(
                self.preview_file_id
            )
        mock_run_job.assert_not_called()

    def test_local_tile_reads_the_low_def_movie_first(self):
        """
        A tile is 100 pixels high: decoding the high def movie for it is
        wasted work.
        """
        tried = []

        def retrieve(_config, _store, prefix, _preview_file):
            tried.append(prefix)
            return None

        with patch.object(
            preview_files_service, "retrieve_preview_file", retrieve
        ):
            self.assertFalse(
                preview_maintenance_service.generate_missing_tile(
                    self.preview_file_id
                )
            )
        self.assertEqual(tried[0], "lowdef")

    @patch("zou.app.services.preview_files_service.retrieve_stored_movie")
    def test_local_tile_builds_run_one_at_a_time(self, mock_retrieve):
        """
        While another local tile build holds the lock, the job gives up
        and forgets its attempt, so a later 404 queues it again.
        """
        attempt_key = preview_maintenance_service._tile_attempt_key(
            self.preview_file_id
        )
        self.redis.set(attempt_key, 1)
        self.redis.set(
            preview_maintenance_service.LOCAL_TILE_BUILD_LOCK_KEY, "x"
        )

        self.assertFalse(
            preview_maintenance_service.generate_missing_tile(
                self.preview_file_id
            )
        )
        mock_retrieve.assert_not_called()
        self.assertFalse(self.redis.exists(attempt_key))


class QueueMissingTilesTestCase(PreviewFileTestCase):
    """
    Queue the tile build of the movies that have none, one job per
    movie, without decoding anything in the command itself.
    """

    def setUp(self):
        super().setUp()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file_id = str(self.preview_file.id)
        self.redis = redis_client.get_client(config.KV_JOB_DB_INDEX)
        self.redis.delete(
            preview_maintenance_service._tile_attempt_key(self.preview_file_id)
        )

    @contextmanager
    def job_queue(self):
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            yield job_queue

    def queued_ids(self, job_queue):
        return [
            call.kwargs["args"][0] for call in job_queue.enqueue.call_args_list
        ]

    def test_a_movie_whose_tile_is_stored_is_left_alone(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.OK
        )
        with self.job_queue() as job_queue, patch.object(
            file_store, "exists_confirmed"
        ) as exists:
            summary = preview_maintenance_service.queue_missing_tiles()
        job_queue.enqueue.assert_not_called()
        exists.assert_not_called()
        self.assertEqual(summary["checked"], 0)
        self.assertEqual(summary["queued"], 0)

    def test_a_probed_stored_tile_is_left_alone(self):
        with self.job_queue() as job_queue, patch.object(
            file_store, "exists_confirmed", return_value=True
        ):
            summary = preview_maintenance_service.queue_missing_tiles()
        job_queue.enqueue.assert_not_called()
        self.assertEqual(summary["stored"], 1)
        self.assertEqual(summary["queued"], 0)

    def test_a_movie_without_tile_is_queued(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        with self.job_queue() as job_queue:
            summary = preview_maintenance_service.queue_missing_tiles()
        self.assertEqual(self.queued_ids(job_queue), [self.preview_file_id])
        self.assertEqual(summary["queued"], 1)

    def test_an_unknown_tile_is_probed_and_recorded(self):
        with self.job_queue() as job_queue, patch.object(
            file_store, "exists_confirmed", return_value=False
        ) as exists:
            summary = preview_maintenance_service.queue_missing_tiles()
        exists.assert_called_once_with(
            "pictures", "tiles", self.preview_file_id
        )
        self.assertEqual(self.queued_ids(job_queue), [self.preview_file_id])
        self.assertEqual(summary["queued"], 1)
        states = states_service.get_file_states(self.preview_file_id)
        self.assertEqual(states["pictures/tiles"]["state"], "missing")

    def test_a_storage_error_skips_the_movie(self):
        with self.job_queue() as job_queue, patch.object(
            file_store, "exists_confirmed", side_effect=RuntimeError("503")
        ):
            summary = preview_maintenance_service.queue_missing_tiles()
        job_queue.enqueue.assert_not_called()
        self.assertEqual(summary["storage_errors"], 1)
        self.assertEqual(
            states_service.get_file_states(self.preview_file_id), {}
        )

    def test_a_recent_attempt_is_skipped_unless_forced(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.FAILED
        )
        self.redis.set(
            preview_maintenance_service._tile_attempt_key(
                self.preview_file_id
            ),
            1,
        )
        with self.job_queue() as job_queue:
            summary = preview_maintenance_service.queue_missing_tiles()
        job_queue.enqueue.assert_not_called()
        self.assertEqual(summary["recently_attempted"], 1)

        with self.job_queue() as job_queue:
            summary = preview_maintenance_service.queue_missing_tiles(
                force=True
            )
        self.assertEqual(self.queued_ids(job_queue), [self.preview_file_id])
        self.assertEqual(summary["queued"], 1)

    def test_limit_caps_the_movies_queued(self):
        stored = self.generate_fixture_preview_file(revision=2)
        states_service.record_file_state(
            str(stored.id), "pictures", "tiles", states_service.OK
        )
        attempted = self.generate_fixture_preview_file(revision=3)
        states_service.record_file_state(
            str(attempted.id), "pictures", "tiles", states_service.FAILED
        )
        self.redis.set(
            preview_maintenance_service._tile_attempt_key(str(attempted.id)), 1
        )
        missing = self.generate_fixture_preview_file(revision=4)
        states_service.record_file_state(
            str(missing.id), "pictures", "tiles", states_service.MISSING
        )
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        try:
            with self.job_queue() as job_queue:
                summary = preview_maintenance_service.queue_missing_tiles(
                    limit=2
                )
        finally:
            self.redis.delete(
                preview_maintenance_service._tile_attempt_key(
                    str(attempted.id)
                )
            )
        self.assertCountEqual(
            self.queued_ids(job_queue),
            [str(missing.id), self.preview_file_id],
        )
        self.assertEqual(summary["queued"], 2)
        self.assertEqual(summary["recently_attempted"], 1)
        self.assertEqual(summary["stored"], 0)

    def test_newest_movies_are_queued_first(self):
        newest = self.generate_fixture_preview_file(revision=2)
        for preview_file_id in [self.preview_file_id, str(newest.id)]:
            states_service.record_file_state(
                preview_file_id, "pictures", "tiles", states_service.MISSING
            )
        with self.job_queue() as job_queue:
            preview_maintenance_service.queue_missing_tiles(limit=1)
        self.assertEqual(self.queued_ids(job_queue), [str(newest.id)])

    def test_pictures_are_not_looked_at(self):
        picture = self.generate_fixture_preview_file(revision=3)
        picture.update({"extension": "png"})
        files_service.clear_preview_file_cache(str(picture.id))
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        with self.job_queue() as job_queue, patch.object(
            file_store, "exists_confirmed", return_value=False
        ):
            summary = preview_maintenance_service.queue_missing_tiles()
        self.assertEqual(self.queued_ids(job_queue), [self.preview_file_id])
        self.assertEqual(summary["checked"], 1)

    def test_nothing_is_queued_without_a_job_queue(self):
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", False
        ):
            self.assertRaises(
                preview_maintenance_service.JobQueueDisabledException,
                preview_maintenance_service.queue_missing_tiles,
            )


class QueueMissingTilesProgressTestCase(QueueMissingTilesTestCase):
    def test_progress_counts_every_movie_looked_at(self):
        self.generate_fixture_preview_file(revision=2)
        states_service.record_file_state(
            self.preview_file_id, "pictures", "tiles", states_service.MISSING
        )
        progress = SpyProgress()
        with self.job_queue(), patch.object(
            file_store, "exists_confirmed", return_value=False
        ):
            preview_maintenance_service.queue_missing_tiles(progress=progress)
        self.assertEqual(progress.total, 2)
        self.assertEqual(progress.advanced, 2)
        self.assertTrue(progress.stopped)

    def test_progress_stops_when_a_movie_fails(self):
        progress = SpyProgress()
        with self.job_queue(), patch.object(
            file_store, "exists_confirmed", side_effect=RuntimeError("503")
        ):
            preview_maintenance_service.queue_missing_tiles(progress=progress)
        self.assertEqual(progress.advanced, 1)
        self.assertTrue(progress.stopped)
