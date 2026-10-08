import os
import shutil
import tempfile

from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from zou.app.services import (
    files_service,
    preview_files_service,
    tasks_service,
)
from zou.app.stores import file_store, queue_store


class BasePreviewDispatchTestCase(ApiDBTestCase):
    """
    A task to attach preview files to and a picture to upload, shared by
    the dispatch test cases without running each other's tests.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_task_status_wip()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.picture_path = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )

    def tearDown(self):
        super().tearDown()
        self.delete_test_folder()

    def create_preview_file(self):
        comment = self.post(
            f"/actions/tasks/{self.task_id}/comment/",
            {"task_status_id": self.wip_status_id, "comment": "c"},
        )
        preview_file = self.post(
            f"/actions/tasks/{self.task_id}"
            f"/comments/{comment['id']}/add-preview",
            {},
        )
        return preview_file["id"]


class PictureUploadDispatchTestCase(BasePreviewDispatchTestCase):
    """
    How a picture upload is handed over: to the RQ queue by default, in
    the request thread when asked for.
    """

    def test_upload_queues_the_variants_and_answers_processing(self):
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}",
                self.picture_path,
            )

        job_queue.enqueue.assert_called_once()
        self.assertEqual(
            job_queue.enqueue.call_args.kwargs["args"][0], preview_file_id
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        # The metadata is read in the request: only the variants wait.
        self.assertEqual(preview_file["status"], "processing")
        self.assertEqual(preview_file["extension"], "png")
        self.assertEqual(preview_file["width"], 180)
        self.assertEqual(preview_file["height"], 101)
        self.assertGreater(preview_file["file_size"], 0)
        self.assertFalse(
            file_store.exists_picture("thumbnails", preview_file_id)
        )

    def test_the_job_stores_the_variants_and_marks_the_preview_ready(self):
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}",
                self.picture_path,
            )
        args = job_queue.enqueue.call_args.kwargs["args"]
        tmp_path = args[1]
        self.assertTrue(os.path.exists(tmp_path))

        preview_files_service.prepare_and_store_picture(*args)

        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["status"], "ready")
        for prefix in [
            "original",
            "thumbnails",
            "thumbnails-square",
            "previews",
        ]:
            self.assertTrue(file_store.exists_picture(prefix, preview_file_id))
        self.assertFalse(os.path.exists(tmp_path))

    def test_no_job_keeps_the_upload_synchronous(self):
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}?no_job=true",
                self.picture_path,
            )
        job_queue.enqueue.assert_not_called()
        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["status"], "ready")
        self.assertTrue(
            file_store.exists_picture("thumbnails", preview_file_id)
        )

    def test_without_a_job_queue_the_upload_stays_synchronous(self):
        preview_file_id = self.create_preview_file()
        self.upload_file(
            f"/pictures/preview-files/{preview_file_id}", self.picture_path
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["status"], "ready")

    def test_a_synchronous_upload_updates_the_task_info_once(self):
        preview_file_id = self.create_preview_file()
        with patch.object(
            tasks_service, "update_preview_file_info"
        ) as update_preview_file_info:
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}",
                self.picture_path,
            )
        update_preview_file_info.assert_called_once()

    def test_a_jpeg_upload_keeps_its_dimensions(self):
        preview_file_id = self.create_preview_file()
        jpeg_path = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.jpg")
        )
        self.upload_file(
            f"/pictures/preview-files/{preview_file_id}", jpeg_path
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["extension"], "png")
        self.assertGreater(preview_file["width"], 0)
        self.assertGreater(preview_file["height"], 0)

    def test_a_job_for_a_deleted_preview_gives_up(self):
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}",
                self.picture_path,
            )
        args = job_queue.enqueue.call_args.kwargs["args"]
        self.delete(f"data/preview-files/{preview_file_id}?force=true")

        # No exception: a preview deleted while its job waited is not a
        # worker crash. update_preview_file waits 1 then 5 seconds for the
        # missing row to show up: the waits are skipped.
        with patch.object(preview_files_service.time, "sleep"):
            preview_files_service.prepare_and_store_picture(*args)

    def test_an_inline_failure_marks_the_preview_broken(self):
        preview_file_id = self.create_preview_file()
        tmp_path = tempfile.mktemp(suffix=".png")
        shutil.copy(self.picture_path, tmp_path)

        with patch.object(
            preview_files_service,
            "save_variants",
            side_effect=RuntimeError("boom"),
        ):
            self.assertRaises(
                RuntimeError,
                preview_files_service.prepare_and_store_picture,
                preview_file_id,
                tmp_path,
            )

        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["status"], "broken")
        self.assertFalse(os.path.exists(tmp_path))


class FrameExtractionDispatchTestCase(BasePreviewDispatchTestCase):
    def test_set_main_preview_with_a_frame_queues_the_extraction(self):
        preview_file_id = self.create_preview_file()
        self.upload_file(
            f"/pictures/preview-files/{preview_file_id}", self.picture_path
        )
        # The endpoint only accepts a frame number for a movie preview;
        # the fixture uploaded above is a picture, so force the extension
        # a real movie upload would have set.
        preview_files_service.update_preview_file(
            preview_file_id, {"extension": "mp4"}
        )
        job_queue = MagicMock()
        with patch.object(
            preview_files_service.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(queue_store, "job_queue", job_queue):
            self.put(
                f"/actions/preview-files/{preview_file_id}/set-main-preview",
                {"frame_number": 12},
            )
        job_queue.enqueue.assert_called_once()
        self.assertEqual(job_queue.enqueue.call_args.kwargs["args"][1], 12)
        # The preview file keeps its status: its variants are still there.
        preview_file = files_service.get_preview_file(preview_file_id)
        self.assertEqual(preview_file["status"], "ready")

    def test_a_failed_extraction_leaves_the_preview_alone(self):
        preview_file_id = self.create_preview_file()
        self.upload_file(
            f"/pictures/preview-files/{preview_file_id}", self.picture_path
        )
        preview_file = files_service.get_preview_file(preview_file_id)
        with patch.object(
            preview_files_service,
            "extract_frame_from_preview_file",
            side_effect=RuntimeError("ffmpeg"),
        ):
            preview_files_service.replace_extracted_frame_for_preview_file(
                preview_file, 12
            )
        self.assertEqual(
            files_service.get_preview_file(preview_file_id)["status"], "ready"
        )


def fail_on_storage_auth(upload_path):
    """
    Job body for StorageRequeueTestCase: a preview job whose upload hit
    a Keystone outage.
    """
    import swiftclient

    exc = swiftclient.ClientException("Authorization Failure. 503")
    return preview_files_service._requeue_on_storage_failure(exc, upload_path)


class StorageRequeueTestCase(BasePreviewDispatchTestCase):
    """
    A preview job whose upload to the object storage fails on Keystone is
    queued again later, its upload kept aside from the TMP_DIR cleaning,
    instead of marking the preview broken.
    """

    def setUp(self):
        super().setUp()
        self.preview_file_id = self.create_preview_file()
        self.tmp_path = os.path.join(
            preview_files_service.config.TMP_DIR, f"{self.preview_file_id}.png"
        )
        os.makedirs(os.path.dirname(self.tmp_path), exist_ok=True)
        shutil.copy(self.picture_path, self.tmp_path)
        self.pending_path = preview_files_service.get_pending_upload_path(
            self.tmp_path
        )
        self.job = MagicMock(meta={}, number_of_retries=None)
        patcher = patch.object(
            preview_files_service, "get_current_job", return_value=self.job
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.is_scheduler_running = preview_files_service.is_scheduler_running
        patcher = patch.object(
            preview_files_service, "is_scheduler_running", return_value=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(
            preview_files_service.remove_temp_files,
            self.tmp_path,
            self.pending_path,
        )

    @staticmethod
    def auth_failure():
        import swiftclient

        return swiftclient.ClientException(
            "Authorization Failure. Authorization failed: "
            "Service Unavailable (HTTP 503)"
        )

    def run_picture_job(self, **patches):
        with patch.object(file_store, "add_picture", **patches):
            return preview_files_service.prepare_and_store_picture(
                self.preview_file_id, self.tmp_path
            )

    def test_picture_job_is_queued_again_with_its_upload_kept(self):
        from rq import Retry

        retry = self.run_picture_job(side_effect=self.auth_failure())

        self.assertIsInstance(retry, Retry)
        self.assertEqual(
            retry.intervals,
            [preview_files_service.STORAGE_RETRY_INTERVALS[0]],
        )
        self.assertFalse(os.path.exists(self.tmp_path))
        self.assertTrue(os.path.exists(self.pending_path))
        self.assertEqual(
            self.job.meta[preview_files_service.STORAGE_RETRIES_META_KEY], 1
        )
        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "processing")

    def test_queued_again_job_stores_the_pending_upload(self):
        self.run_picture_job(side_effect=self.auth_failure())

        # Same arguments: the job finds its upload in the pending folder.
        preview_files_service.prepare_and_store_picture(
            self.preview_file_id, self.tmp_path
        )

        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "ready")
        self.assertTrue(
            file_store.exists_picture("original", self.preview_file_id)
        )
        self.assertFalse(os.path.exists(self.pending_path))

    def test_exhausted_attempts_mark_the_preview_broken(self):
        self.job.meta[preview_files_service.STORAGE_RETRIES_META_KEY] = len(
            preview_files_service.STORAGE_RETRY_INTERVALS
        )
        with self.assertRaises(Exception):
            self.run_picture_job(side_effect=self.auth_failure())

        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "broken")
        self.assertFalse(os.path.exists(self.tmp_path))

    def test_other_errors_mark_the_preview_broken(self):
        with self.assertRaises(RuntimeError):
            self.run_picture_job(side_effect=RuntimeError("boom"))

        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "broken")
        self.assertFalse(os.path.exists(self.pending_path))

    def test_inline_processing_is_not_queued_again(self):
        preview_files_service.get_current_job.return_value = None
        with self.assertRaises(Exception):
            self.run_picture_job(side_effect=self.auth_failure())

        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "broken")

    def test_without_a_scheduler_the_preview_is_broken_at_once(self):
        # A delayed retry is only queued again by a worker started with
        # --with-scheduler: without one the preview would stay
        # "processing" forever.
        preview_files_service.is_scheduler_running.return_value = False
        with self.assertRaises(Exception):
            self.run_picture_job(side_effect=self.auth_failure())

        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "broken")
        self.assertFalse(os.path.exists(self.pending_path))
        self.assertNotIn(
            preview_files_service.STORAGE_RETRIES_META_KEY, self.job.meta
        )

    def test_movie_job_is_queued_again_with_its_upload_kept(self):
        from rq import Retry

        self.job.meta[
            preview_files_service.remote_job.NOMAD_JOB_ID_META_KEY
        ] = "zou-normalize/dispatch-1"
        with patch.object(
            preview_files_service,
            "_process_movie",
            side_effect=self.auth_failure(),
        ):
            retry = preview_files_service.prepare_and_store_movie(
                self.preview_file_id, self.tmp_path
            )

        self.assertIsInstance(retry, Retry)
        self.assertTrue(os.path.exists(self.pending_path))
        # The next attempt starts over instead of resuming the Nomad job.
        self.assertNotIn(
            preview_files_service.remote_job.NOMAD_JOB_ID_META_KEY,
            self.job.meta,
        )
        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "processing")

    def test_failure_callback_removes_the_pending_upload(self):
        self.run_picture_job(side_effect=self.auth_failure())
        job = MagicMock(args=(self.preview_file_id, self.tmp_path))

        preview_files_service.mark_broken_on_job_failure(
            job, None, RuntimeError, RuntimeError("timeout"), None
        )

        self.assertFalse(os.path.exists(self.pending_path))
        preview_file = files_service.get_preview_file(self.preview_file_id)
        self.assertEqual(preview_file["status"], "broken")

    def test_rq_schedules_the_job_for_later(self):
        import fakeredis
        from rq import Queue, get_current_job
        from rq.job import JobStatus
        from rq.scheduler import RQScheduler

        from zou.app.utils.job_worker import ZouJob, ZouWorker

        # The real job this time, run the way a job process runs it.
        preview_files_service.get_current_job.side_effect = get_current_job
        preview_files_service.is_scheduler_running.side_effect = (
            self.is_scheduler_running
        )
        connection = fakeredis.FakeStrictRedis()
        # What a worker started with --with-scheduler holds.
        connection.set(RQScheduler.get_locking_key("test"), 1234)
        queue = Queue("test", connection=connection, job_class=ZouJob)
        worker = ZouWorker([queue], connection=connection)
        queue.enqueue(fail_on_storage_auth, self.tmp_path)
        job = queue.dequeue_any(
            [queue], None, connection=connection, job_class=ZouJob
        )[0]
        worker.prepare_execution(job)
        worker.perform_job(job, queue)

        job = ZouJob.fetch(job.id, connection=connection)
        self.assertEqual(job.get_status(), JobStatus.SCHEDULED)
        self.assertEqual(
            job.meta[preview_files_service.STORAGE_RETRIES_META_KEY], 1
        )
        self.assertIn(job.id, queue.scheduled_job_registry.get_job_ids())

    def test_scheduler_is_detected_from_its_lock(self):
        import fakeredis
        from rq.scheduler import RQScheduler

        connection = fakeredis.FakeStrictRedis()
        job = MagicMock(origin="test", connection=connection)
        self.assertFalse(self.is_scheduler_running(job))
        connection.set(RQScheduler.get_locking_key("test"), 1234)
        self.assertTrue(self.is_scheduler_running(job))
