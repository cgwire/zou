import os
import shutil
import tempfile
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from tests.services.cases import PreviewFileTestCase, SpyProgress
from zou.app import config
from zou.app.exceptions import EpisodeNotFoundException
from zou.app.models.preview_file import PreviewFile
from zou.app.models.project import Project
from zou.app.services import (
    files_service,
    preview_file_states_service as states_service,
    preview_files_service,
    preview_maintenance_service,
)
from zou.app.stores import file_store, queue_store, redis_client
from zou.app.utils import fs, thumbnail as thumbnail_utils
from zou.utils import movie


def store_original_picture(preview_file_id):
    path = file_store.get_local_picture_path("original", preview_file_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile("tests/fixtures/thumbnails/th01.png", path)
    return path


def store_movie(preview_file_id):
    path = file_store.get_local_movie_path("previews", preview_file_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile("tests/fixtures/videos/test_preview_tiles.mp4", path)
    return path


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

    def test_reset_picture_files_metadata(self):
        path = store_original_picture(str(self.preview_file.id))
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
        path = store_movie(str(self.preview_file.id))

        preview_maintenance_service.reset_movie_files_metadata()

        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual(
            (preview_file.width, preview_file.height),
            movie.get_movie_size(path),
        )
        self.assertEqual(preview_file.file_size, os.path.getsize(path))
        self.assertGreater(preview_file.duration, 0)

    def test_a_missing_movie_does_not_stop_the_run(self):
        before = PreviewFile.get(self.preview_file.id).updated_at

        preview_maintenance_service.reset_movie_files_metadata()

        self.assertEqual(
            PreviewFile.get(self.preview_file.id).updated_at, before
        )


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
        The attempt mark is kept in Redis, with the retry delay as its
        lifetime: a second attempt within that delay queues nothing.
        """
        with self.job_queue() as job_queue:
            self.assertTrue(
                preview_maintenance_service.generate_tile_later(
                    self.preview_file_id
                )
            )
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

    @patch("zou.app.services.preview_files_service.remote_job.run_job")
    def test_a_movie_not_ready_gets_no_tile(self, mock_run_job):
        """
        A movie still in processing has no stored binary yet: no job may
        run for it.
        """
        self.preview_file.update({"status": "processing"})
        files_service.clear_preview_file_cache(self.preview_file_id)

        with self.remote_tile_job():
            self.assertFalse(
                preview_maintenance_service.generate_missing_tile(
                    self.preview_file_id
                )
            )
        mock_run_job.assert_not_called()


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


class GeneratePreviewExtraTestCase(PreviewFileTestCase):
    def test_preview_extra_keeps_the_metadata_on_a_transient_failure(self):
        movie_fixture = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        self.generate_fixture_preview_file()
        self.preview_file.update({"width": 1920, "height": 1080})

        def high_def_hiccup(config, get_path, open_file, prefix, *args, **kw):
            if prefix == "previews":
                raise preview_files_service.fs.FileNotFound("previews-x")
            return movie_fixture

        with patch.object(
            preview_files_service.fs,
            "get_file_path_and_file",
            side_effect=high_def_hiccup,
        ):
            preview_maintenance_service.generate_preview_extra(
                with_metadata=True
            )
        preview_file = PreviewFile.get(self.preview_file.id)
        self.assertEqual(preview_file.width, 1920)
        self.assertEqual(preview_file.height, 1080)

    def a_picture(self):
        preview_file = self.generate_fixture_preview_file()
        preview_file.update({"extension": "png"})
        return preview_file

    def test_preview_extra_reads_the_size_of_a_picture(self):
        preview_file = self.a_picture()
        path = store_original_picture(str(preview_file.id))

        preview_maintenance_service.generate_preview_extra(with_metadata=True)

        preview_file = PreviewFile.get(preview_file.id)
        self.assertEqual(
            (preview_file.width, preview_file.height),
            thumbnail_utils.get_dimensions(path),
        )
        self.assertEqual(preview_file.file_size, os.path.getsize(path))
        self.assertIsNone(preview_file.duration)

    def test_preview_extra_builds_the_thumbnails_of_a_picture(self):
        preview_file_id = str(self.a_picture().id)
        store_original_picture(preview_file_id)

        preview_maintenance_service.generate_preview_extra(
            with_thumbnails=True
        )

        self.assertTrue(
            file_store.exists_picture("thumbnails", preview_file_id)
        )

    def test_preview_extra_builds_the_tile_of_a_movie(self):
        preview_file_id = str(self.generate_fixture_preview_file().id)
        store_movie(preview_file_id)
        tile_folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tile_folder, True)
        tile_path = os.path.join(tile_folder, "tile.png")
        shutil.copyfile("tests/fixtures/thumbnails/th01.png", tile_path)

        with patch.object(
            preview_files_service.movie,
            "generate_tile",
            return_value=tile_path,
        ):
            preview_maintenance_service.generate_preview_extra(with_tiles=True)

        self.assertTrue(file_store.exists_picture("tiles", preview_file_id))

    def run_on_object_storage(self, downloaded_path):
        with patch.object(config, "FS_BACKEND", "s3"), patch.object(
            preview_files_service,
            "retrieve_preview_file",
            return_value=downloaded_path,
        ):
            preview_maintenance_service.generate_preview_extra()

    def test_object_storage_download_is_removed_after_use(self):
        """
        On object storage, each preview is downloaded to the temp folder:
        a run over the whole store must not fill the disk.
        """
        self.a_picture()
        os.makedirs(config.TMP_DIR, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=config.TMP_DIR, suffix=".png")
        os.close(fd)
        self.addCleanup(fs.rm_file, path)

        self.run_on_object_storage(path)

        self.assertFalse(os.path.exists(path))

    def test_object_storage_cache_entry_is_kept(self):
        """
        A file that was already in the read cache belongs to the cache:
        the command does not remove it.
        """
        preview_file_id = str(self.a_picture().id)
        os.makedirs(config.TMP_DIR, exist_ok=True)
        path = os.path.join(
            config.TMP_DIR, f"cache-original-{preview_file_id}.png"
        )
        open(path, "wb").close()
        self.addCleanup(fs.rm_file, path)

        self.run_on_object_storage(path)

        self.assertTrue(os.path.exists(path))


class PreviewExtraQueryTestCase(PreviewFileTestCase):
    """
    The selection of the preview extra commands. A filter that does not
    apply makes the command process the whole store again.
    """

    def setUp(self):
        super().setUp()
        self.asset_preview = self.generate_fixture_preview_file()
        self.episodes = []
        self.shots = []
        self.shot_previews = []
        for name in ["E01", "E02"]:
            episode = self.generate_fixture_episode(name)
            sequence = self.generate_fixture_sequence(
                f"S-{name}", episode_id=episode.id
            )
            shot = self.generate_fixture_shot(
                f"P-{name}", sequence_id=sequence.id
            )
            task = self.generate_fixture_task(entity_id=shot.id)
            self.episodes.append(episode)
            self.shots.append(shot)
            self.shot_previews.append(
                self.generate_fixture_preview_file(task_id=task.id)
            )
        other_project = Project.create(
            name="Other", project_status_id=self.open_status.id
        )
        other_asset = self.generate_fixture_asset(
            name="Rock", project_id=other_project.id
        )
        other_task = self.generate_fixture_task(
            entity_id=other_asset.id, project_id=other_project.id
        )
        self.other_preview = self.generate_fixture_preview_file(
            task_id=other_task.id
        )

    def selected(self, **filters):
        query = preview_maintenance_service._build_preview_extra_query(
            **filters
        )
        return {str(preview_file.id) for preview_file in query}

    def ids(self, *preview_files):
        return {str(preview_file.id) for preview_file in preview_files}

    def test_project_given_by_name(self):
        self.assertEqual(
            self.selected(project="Cosmos Landromat"),
            self.ids(self.asset_preview, *self.shot_previews),
        )

    def test_project_given_by_id(self):
        self.assertEqual(
            self.selected(project=self.project_id),
            self.ids(self.asset_preview, *self.shot_previews),
        )

    def test_entity(self):
        self.assertEqual(
            self.selected(entity_id=str(self.shots[0].id)),
            self.ids(self.shot_previews[0]),
        )

    def test_episode_given_by_id(self):
        self.assertEqual(
            self.selected(episodes=[str(self.episodes[0].id)]),
            self.ids(self.shot_previews[0]),
        )

    def test_episode_given_by_name_in_a_project(self):
        self.assertEqual(
            self.selected(project="Cosmos Landromat", episodes=["E01"]),
            self.ids(self.shot_previews[0]),
        )

    def test_episode_name_needs_a_project(self):
        self.assertRaises(
            EpisodeNotFoundException, self.selected, episodes=["E01"]
        )

    def test_only_shots(self):
        self.assertEqual(
            self.selected(only_shots=True), self.ids(*self.shot_previews)
        )

    def test_only_assets(self):
        self.assertEqual(
            self.selected(only_assets=True),
            self.ids(self.asset_preview, self.other_preview),
        )
