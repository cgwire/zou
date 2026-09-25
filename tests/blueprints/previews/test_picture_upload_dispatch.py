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


class PictureUploadDispatchTestCase(ApiDBTestCase):
    """
    How a picture upload is handed over: to the RQ queue by default, in
    the request thread when asked for.
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
        # worker crash.
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


class FrameExtractionDispatchTestCase(PictureUploadDispatchTestCase):
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
