import os
import tempfile
import unittest

from zou.app.services import sync_service


class DownloadFileTestCase(unittest.TestCase):
    def test_partial_file_removed_on_error(self):
        folder = tempfile.mkdtemp()
        file_path = os.path.join(folder, "preview.mp4")

        def failing_dl_func(prefix, preview_file_id):
            yield b"partial content"
            raise RuntimeError("stream interrupted")

        sync_service.download_file(
            file_path, "previews", failing_dl_func, "preview-id"
        )
        self.assertFalse(os.path.exists(file_path))

    def test_successful_download_keeps_file(self):
        folder = tempfile.mkdtemp()
        file_path = os.path.join(folder, "preview.mp4")

        def dl_func(prefix, preview_file_id):
            yield b"full content"

        sync_service.download_file(
            file_path, "previews", dl_func, "preview-id"
        )
        with open(file_path, "rb") as downloaded:
            self.assertEqual(downloaded.read(), b"full content")
