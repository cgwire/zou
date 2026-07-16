import os

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.services import preview_files_service


class PreviewProcessingFailureTestCase(ApiDBTestCase):
    """
    A server-side movie processing failure (ffmpeg, storage...) must be
    reported as a 500 with the underlying reason, not as a 400 mislabelled
    as a normalization problem.
    """

    def setUp(self):
        super(PreviewProcessingFailureTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.wip_status_id = str(self.task_status_wip.id)

    def add_movie_preview(self):
        """
        Create a comment, attach a preview slot and return the movie path.
        """
        path = f"/actions/tasks/{self.task_id}/comment/"
        comment = self.post(
            path,
            {"task_status_id": self.wip_status_id, "comment": "c"},
        )
        path = (
            f"/actions/tasks/{self.task_id}"
            f"/comments/{comment['id']}/add-preview"
        )
        preview_file = self.post(path, {})
        movie_path = self.get_fixture_file_path(
            os.path.join("videos", "test_preview_tiles.mp4")
        )
        return preview_file["id"], movie_path

    @mock.patch(
        "zou.app.services.preview_files_service.prepare_and_store_movie"
    )
    def test_processing_failure_returns_500_with_reason(self, mocked):
        mocked.side_effect = Exception("ffmpeg exploded")
        preview_file_id, movie_path = self.add_movie_preview()

        response = self.upload_file(
            f"/pictures/preview-files/{preview_file_id}?normalize=false",
            movie_path,
            code=500,
        )
        message = response.get("message", "")
        self.assertIn("processing failed", message)
        self.assertIn("normalization disabled", message)
        self.assertEqual(
            response.get("data", {}).get("reason"), "ffmpeg exploded"
        )

    @mock.patch("zou.app.config.ENABLE_JOB_QUEUE", True)
    @mock.patch("zou.app.stores.queue_store.job_queue")
    def test_movie_upload_enqueues_with_failure_callback(self, mock_queue):
        """
        The movie normalization job must carry an on_failure callback so a
        killed worker cannot leave the preview file stuck in "processing".
        """
        preview_file_id, movie_path = self.add_movie_preview()

        self.upload_file(
            f"/pictures/preview-files/{preview_file_id}", movie_path
        )

        self.assertTrue(mock_queue.enqueue.called)
        kwargs = mock_queue.enqueue.call_args.kwargs
        self.assertEqual(
            kwargs.get("on_failure"),
            preview_files_service.mark_broken_on_job_failure,
        )
