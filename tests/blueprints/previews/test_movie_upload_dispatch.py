import os

from unittest.mock import MagicMock, patch

from tests.base import ApiDBTestCase
from zou.app.blueprints.previews import resources as preview_resources


class MovieUploadDispatchTestCase(ApiDBTestCase):
    """
    How a movie upload is handed over: to the RQ queue, to the remote
    worker, or processed in the request thread.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_task_status_wip()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)
        self.movie_path = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
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

    def test_remote_setup_queues_the_job_even_without_normalization(self):
        """
        The remote worker is what builds the thumbnails and the tile, so it
        must be dispatched anyway, and never from the request thread since
        waiting for Nomad would hold the connection open.
        """
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()

        with patch.object(
            preview_resources.preview_files_service,
            "is_remote_normalization_enabled",
            return_value=True,
        ), patch.object(
            preview_resources.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(
            preview_resources.config, "PREVIEW_SAVE_SOURCE_FILE", False
        ), patch.object(
            preview_resources.queue_store, "job_queue", job_queue
        ):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}?normalize=false",
                self.movie_path,
            )

        job_queue.enqueue.assert_called_once()
        args = job_queue.enqueue.call_args.kwargs["args"]
        self.assertEqual(args[0], preview_file_id)
        # normalize is passed through, and the source is uploaded whatever
        # PREVIEW_SAVE_SOURCE_FILE says: the remote worker reads it from the
        # object storage.
        self.assertFalse(args[2])
        self.assertTrue(args[3])

    def test_local_setup_without_normalization_stays_synchronous(self):
        preview_file_id = self.create_preview_file()
        job_queue = MagicMock()

        with patch.object(
            preview_resources.preview_files_service,
            "is_remote_normalization_enabled",
            return_value=False,
        ), patch.object(
            preview_resources.config, "ENABLE_JOB_QUEUE", True
        ), patch.object(
            preview_resources.queue_store, "job_queue", job_queue
        ):
            self.upload_file(
                f"/pictures/preview-files/{preview_file_id}?normalize=false",
                self.movie_path,
            )

        job_queue.enqueue.assert_not_called()
        preview_file = self.get(f"data/preview-files/{preview_file_id}")
        self.assertEqual(preview_file["status"], "ready")
