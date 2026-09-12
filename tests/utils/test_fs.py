import os
import time
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
        # Sleeping three seconds and asking again for an object that is
        # not there delays every fallback on the next prefix.
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

        exception = fs.download_to_file(
            self.file_path, open_file, "previews", "id"
        )

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

        exception = fs.download_to_file(
            self.file_path, open_file, "previews", "id"
        )

        self.assertIsInstance(exception, IOError)
        with open(self.file_path, "rb") as cached:
            self.assertEqual(cached.read(), b"complete-movie")
        self.assertEqual(self.cache_files(), ["cache-previews-id"])

    def test_failed_download_writes_no_cache_entry(self):
        def open_file(prefix, instance_id):
            raise IOError("connection reset")
            yield b""

        fs.download_to_file(self.file_path, open_file, "previews", "id")

        self.assertFalse(os.path.exists(self.file_path))
        self.assertEqual(self.cache_files(), [])

    def test_stale_part_is_swept_and_live_one_kept(self):
        # A download killed with its process leaves its .part behind.
        stale_path = f"{self.file_path}.dead.part"
        live_path = f"{self.file_path}.live.part"
        for path in (stale_path, live_path):
            with open(path, "wb") as part:
                part.write(b"partial")
        old = os.path.getmtime(stale_path) - fs.STALE_PART_AGE - 1
        os.utime(stale_path, (old, old))

        def open_file(prefix, instance_id):
            yield b"movie"

        fs.download_to_file(self.file_path, open_file, "previews", "id")

        self.assertEqual(
            self.cache_files(),
            ["cache-previews-id", "cache-previews-id.live.part"],
        )

    def test_concurrent_download_is_served_instead_of_a_404(self):
        # The other request completed the cache entry while this one was
        # failing: serving it beats answering a 404, and beats retrying.
        config = FakeConfig(self.tmp_dir.name)
        cache_path = fs.get_cache_file_path(config, "previews", "id", "mp4")

        def open_file(prefix, instance_id):
            with open(cache_path, "wb") as cached:
                cached.write(b"complete-movie")
            raise IOError("connection reset")
            yield b""

        with mock.patch("zou.app.utils.fs.time.sleep") as sleep:
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
        sleep.assert_not_called()


class FillCacheInBackgroundTestCase(unittest.TestCase):
    def wait_for(self, path):
        import time

        for _ in range(100):
            if os.path.exists(path):
                return
            time.sleep(0.05)
        self.fail(f"{path} never appeared")

    def test_unwritable_cache_dir_does_not_fail_the_request(self):
        # The request can be streamed from the storage without any disk:
        # a full or read-only TMP_DIR only means no cache fill.
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "missing", "cache-lowdef-1.mp4")
            self.assertFalse(
                fs.fill_cache_in_background(file_path, None, "lowdef", "1")
            )

    def test_failed_fill_is_logged(self):
        def open_file(prefix, instance_id):
            raise RuntimeError("credentials rotated")
            yield

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "cache-lowdef-1.mp4")
            with self.assertLogs("zou.app.utils.fs", level="ERROR") as logs:
                self.assertTrue(
                    fs.fill_cache_in_background(
                        file_path, open_file, "lowdef", "1"
                    )
                )
                self.wait_for(f"{file_path}.lock")
                for _ in range(100):
                    if logs.output:
                        break
                    time.sleep(0.05)
        self.assertIn("credentials rotated", logs.output[0])
        self.assertIn("lowdef-1", logs.output[0])

    def test_concurrent_fills_are_capped(self):
        import threading

        release = threading.Event()

        def open_file(prefix, instance_id):
            release.wait(5)
            yield b"movie"

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = [
                os.path.join(tmp_dir, f"cache-lowdef-{i}.mp4")
                for i in range(fs.MAX_CONCURRENT_CACHE_FILLS + 1)
            ]
            started = [
                fs.fill_cache_in_background(path, open_file, "lowdef", str(i))
                for i, path in enumerate(paths)
            ]
            self.assertEqual(
                started, [True] * fs.MAX_CONCURRENT_CACHE_FILLS + [False]
            )
            release.set()
            for path in paths[:-1]:
                self.wait_for(path)
            # A finished fill gives its slot back.
            self.assertTrue(
                fs.fill_cache_in_background(
                    paths[-1], open_file, "lowdef", "x"
                )
            )
            self.wait_for(paths[-1])

    def test_downloads_once_under_the_lock(self):
        import fcntl

        calls = []

        def open_file(prefix, instance_id):
            calls.append(instance_id)
            yield b"movie"

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = os.path.join(tmp_dir, "cache-lowdef-1.mp4")
            lock_file = open(f"{file_path}.lock", "a")
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Another worker is downloading: do not start a second one.
            self.assertFalse(
                fs.fill_cache_in_background(
                    file_path, open_file, "lowdef", "1"
                )
            )
            self.assertEqual(calls, [])
            lock_file.close()

            self.assertTrue(
                fs.fill_cache_in_background(
                    file_path, open_file, "lowdef", "1"
                )
            )
            self.wait_for(file_path)
            with open(file_path, "rb") as cached:
                self.assertEqual(cached.read(), b"movie")
            self.assertEqual(calls, ["1"])
