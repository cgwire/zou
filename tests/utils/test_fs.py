import os
import tempfile
import unittest
from unittest import mock

import pytest
from flask_fs.errors import FileNotFound

from zou.app.utils import fs


class FakeConfig:
    FS_BACKEND = "s3"

    def __init__(self, tmp_dir):
        self.TMP_DIR = tmp_dir


class MkdirTestCase(unittest.TestCase):
    def test_mkdirp(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = os.path.join(tmp_dir, "one")
            folder = os.path.join(root, "two", "three")
            fs.mkdir_p(folder)
            self.assertTrue(os.path.exists(folder))
            fs.rm_rf(root)
            self.assertTrue(not os.path.exists(folder))


class GetFilePathAndFileTestCase(unittest.TestCase):
    def test_missing_remote_file_raises_file_not_found(self):
        # A remote download that "succeeds" but yields an empty file must be
        # reported as absent (FileNotFound -> 404), not an unhandled 500.
        def open_file(prefix, instance_id):
            yield from ()

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("zou.app.utils.fs.time.sleep"):
                with pytest.raises(FileNotFound):
                    fs.get_file_path_and_file(
                        FakeConfig(tmp_dir),
                        get_local_path=lambda prefix, instance_id: "",
                        open_file=open_file,
                        prefix="previews",
                        instance_id="does-not-exist",
                        extension="png",
                    )

    def test_missing_object_is_not_retried(self):
        # Swift and S3 do not raise FileNotFound: they surface their own
        # exception carrying a 404. Sleeping three seconds and asking
        # again for an object that is not there delays every fallback on
        # the next prefix.
        class SwiftClientException(Exception):
            http_status = 404

        calls = []

        def open_file(prefix, instance_id):
            calls.append(prefix)
            raise SwiftClientException("Object GET failed: 404 Not Found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("zou.app.utils.fs.time.sleep") as sleep:
                with pytest.raises(FileNotFound):
                    fs.get_file_path_and_file(
                        FakeConfig(tmp_dir),
                        get_local_path=lambda prefix, instance_id: "",
                        open_file=open_file,
                        prefix="lowdef",
                        instance_id="does-not-exist",
                        extension="mp4",
                    )
                sleep.assert_not_called()
        self.assertEqual(calls, ["lowdef"])

    def test_transient_error_is_retried(self):
        class ServerError(Exception):
            http_status = 503

        calls = []

        def open_file(prefix, instance_id):
            calls.append(prefix)
            raise ServerError("Service Unavailable")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch("zou.app.utils.fs.time.sleep") as sleep:
                with pytest.raises(FileNotFound):
                    fs.get_file_path_and_file(
                        FakeConfig(tmp_dir),
                        get_local_path=lambda prefix, instance_id: "",
                        open_file=open_file,
                        prefix="lowdef",
                        instance_id="does-not-exist",
                        extension="mp4",
                    )
                sleep.assert_called_once()
        self.assertEqual(calls, ["lowdef", "lowdef"])


class IsMissingFileErrorTestCase(unittest.TestCase):
    def test_file_not_found(self):
        self.assertTrue(fs.is_missing_file_error(FileNotFound("key")))

    def test_swift_client_exception(self):
        exception = Exception("Object GET failed")
        exception.http_status = 404
        self.assertTrue(fs.is_missing_file_error(exception))

    def test_botocore_client_error(self):
        exception = Exception("An error occurred (NoSuchKey)")
        exception.response = {
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        }
        self.assertTrue(fs.is_missing_file_error(exception))

    def test_transient_errors(self):
        self.assertFalse(fs.is_missing_file_error(None))
        self.assertFalse(fs.is_missing_file_error(IOError("connection")))
        exception = Exception("Service Unavailable")
        exception.http_status = 503
        self.assertFalse(fs.is_missing_file_error(exception))


class DownloadToFileTestCase(unittest.TestCase):
    """
    The cache entry is written through a temporary file: a download that
    fails halfway must leave neither a truncated file nor a hole where a
    concurrent request was reading.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.file_path = os.path.join(self.tmp_dir.name, "cache-previews-id")

    def cache_files(self):
        return sorted(os.listdir(self.tmp_dir.name))

    def test_download_replaces_the_cache_entry(self):
        def open_file(prefix, instance_id):
            yield b"movie"
            yield b"-bytes"

        download_failed, exception = fs._download_to_file(
            self.file_path, open_file, "previews", "id"
        )

        self.assertFalse(download_failed)
        self.assertIsNone(exception)
        with open(self.file_path, "rb") as cached:
            self.assertEqual(cached.read(), b"movie-bytes")
        self.assertEqual(self.cache_files(), ["cache-previews-id"])

    def test_interrupted_download_leaves_the_cache_untouched(self):
        with open(self.file_path, "wb") as cached:
            cached.write(b"complete-movie")

        def open_file(prefix, instance_id):
            yield b"trunc"
            raise IOError("connection reset")

        download_failed, exception = fs._download_to_file(
            self.file_path, open_file, "previews", "id"
        )

        self.assertTrue(download_failed)
        self.assertIsInstance(exception, IOError)
        with open(self.file_path, "rb") as cached:
            self.assertEqual(cached.read(), b"complete-movie")
        self.assertEqual(self.cache_files(), ["cache-previews-id"])

    def test_failed_download_writes_no_cache_entry(self):
        def open_file(prefix, instance_id):
            raise IOError("connection reset")
            yield b""

        fs._download_to_file(self.file_path, open_file, "previews", "id")

        self.assertFalse(os.path.exists(self.file_path))
        self.assertEqual(self.cache_files(), [])

    def test_concurrent_download_is_served_instead_of_a_404(self):
        # The other request completed the cache entry while this one was
        # failing: serving it beats answering a 404.
        config = FakeConfig(self.tmp_dir.name)
        cache_path = fs.get_cache_file_path(config, "previews", "id", "mp4")

        def open_file(prefix, instance_id):
            with open(cache_path, "wb") as cached:
                cached.write(b"complete-movie")
            raise IOError("connection reset")
            yield b""

        with mock.patch("zou.app.utils.fs.time.sleep"):
            file_path = fs.get_file_path_and_file(
                config,
                get_local_path=lambda prefix, instance_id: "",
                open_file=open_file,
                prefix="previews",
                instance_id="id",
                extension="mp4",
            )

        with open(file_path, "rb") as cached:
            self.assertEqual(cached.read(), b"complete-movie")
