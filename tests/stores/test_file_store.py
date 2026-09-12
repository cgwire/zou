import unittest
import os

from unittest.mock import Mock

import pytest
from flask_fs.errors import FileNotFound

from zou.app import app
from zou.app.stores import file_store


class FileStoreTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        app.app_context().push()
        self.preview_path = app.config["PREVIEW_FOLDER"]
        self.store = file_store
        self.store.clear()

    def tearDown(self):
        super().tearDown()
        self.store.clear()

    def get_fixture_file_path(self, relative_path):
        current_path = os.getcwd()
        file_path_fixture = os.path.join(
            current_path, "tests", "fixtures", relative_path
        )
        return file_path_fixture

    def test_path(self):
        file_name = "thumbnails-63e453f1-9655-49ad-acba-ff7f27c49e9d"
        self.assertEqual(
            file_store.path(file_store.pictures, file_name),
            os.path.join(
                self.preview_path,
                "pictures/thumbnails/63e/453/"
                "63e453f1-9655-49ad-acba-ff7f27c49e9d",
            ),
        )

    def test_path_dbbackup(self):
        file_name = "dbbackup-zou-db-backup-2026-02-24T09:42:21.sql.gz"
        result = file_store.path(file_store.files, file_name)
        self.assertTrue(
            result.endswith(
                os.path.join(
                    "files",
                    "dbbackup",
                    "zou-db-backup-2026-02-24T09:42:21.sql.gz",
                )
            )
        )
        self.assertNotIn("/-db/", result)

    def test_add_and_open_picture(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        file_store.add_picture(
            "thumbnails",
            "63e453f1-9655-49ad-acba-ff7f27c49e9d",
            file_path_fixture,
        )
        file_name = "thumbnails-63e453f1-9655-49ad-acba-ff7f27c49e9d"
        result_path = file_store.path(file_store.pictures, file_name)
        self.assertTrue(os.path.exists(result_path))


class ReadGeneratorTestCase(unittest.TestCase):
    """
    flask_fs turns every backend error into FileNotFound because its
    existence check swallows them. The read generator has to keep a
    missing object and a transient failure apart: only the former is
    worth skipping the download retry for.
    """

    def make_bucket(self, error):
        bucket = Mock()
        bucket.backend.encryptor = None
        bucket.backend.read_chunks.side_effect = error
        return bucket

    def test_missing_object_is_a_file_not_found(self):
        error = Exception("Object GET failed")
        error.http_status = 404
        with pytest.raises(FileNotFound):
            file_store.make_read_generator(self.make_bucket(error), "key")

    def test_transient_failure_is_left_alone(self):
        error = Exception("Service Unavailable")
        error.http_status = 503
        with pytest.raises(Exception, match="Service Unavailable"):
            file_store.make_read_generator(self.make_bucket(error), "key")

    def test_missing_local_file_is_a_file_not_found(self):
        app.app_context().push()
        with pytest.raises(FileNotFound):
            list(file_store.open_picture("thumbnails", "does-not-exist"))


class SwiftConnectionPerThreadTestCase(unittest.TestCase):
    def test_swift_reads_never_share_the_backend_connection(self):
        # swiftclient.Connection is not thread-safe: the request thread
        # (range read) and the cache fill thread (chunked read) must each
        # use their own, never the one flask_fs holds on the backend.
        import threading
        from unittest.mock import patch

        connections = []

        class FakeConnection:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                connections.append(self)

            def get_object(self, container, key, **kwargs):
                return {"content-length": "2"}, iter([b"ab"])

        shared = Mock()
        shared.get_object.side_effect = AssertionError("shared connection")
        shared.authurl, shared.user, shared.key = "url", "user", "key"
        shared.auth_version, shared.os_options, shared.retries = "3", {}, 5
        movies = Mock()
        movies.backend.encryptor = None
        movies.backend.name = "movies"
        movies.backend.conn = shared
        results = []

        with (
            patch.object(file_store, "movies", movies),
            patch.object(file_store.config, "FS_BACKEND", "swift"),
            patch("swiftclient.Connection", FakeConnection),
        ):
            _, _, generator = file_store.read_movie_range("lowdef", "1")
            results.append(b"".join(generator))
            thread = threading.Thread(
                target=lambda: results.append(
                    b"".join(file_store.open_movie("lowdef", "1"))
                )
            )
            thread.start()
            thread.join()

        self.assertEqual(results, [b"ab", b"ab"])
        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[0].kwargs["authurl"], "url")


class ReadMovieRangeTestCase(unittest.TestCase):
    def test_s3_range_is_forwarded_and_the_body_closed(self):
        from unittest.mock import patch

        body = Mock()
        body.iter_chunks.return_value = iter([b"ab", b"cd"])
        s3_object = Mock()
        s3_object.get.return_value = {
            "Body": body,
            "ContentLength": 4,
            "ContentRange": "bytes 10-13/100",
        }
        movies = Mock()
        movies.backend.encryptor = None
        movies.backend.bucket.Object.return_value = s3_object

        with (
            patch.object(file_store, "movies", movies),
            patch.object(file_store.config, "FS_BACKEND", "s3"),
        ):
            self.assertTrue(file_store.can_stream_movie_ranges())
            length, content_range, generator = file_store.read_movie_range(
                "lowdef", "1", "bytes=10-13"
            )
            self.assertEqual(b"".join(generator), b"abcd")

        movies.backend.bucket.Object.assert_called_once_with("lowdef-1")
        s3_object.get.assert_called_once_with(Range="bytes=10-13")
        self.assertEqual((length, content_range), (4, "bytes 10-13/100"))
        body.close.assert_called_once()

    def test_missing_object_is_file_not_found(self):
        from unittest.mock import patch

        class ClientError(Exception):
            response = {"Error": {"Code": "NoSuchKey"}}

        movies = Mock()
        movies.backend.bucket.Object.return_value.get.side_effect = (
            ClientError()
        )
        with (
            patch.object(file_store, "movies", movies),
            patch.object(file_store.config, "FS_BACKEND", "s3"),
        ):
            with pytest.raises(FileNotFound):
                file_store.read_movie_range("lowdef", "1", "bytes=0-1")

    def test_refused_range_is_a_416(self):
        from unittest.mock import patch
        from werkzeug.exceptions import RequestedRangeNotSatisfiable

        class ClientError(Exception):
            response = {"Error": {"Code": "InvalidRange"}}

        movies = Mock()
        movies.backend.bucket.Object.return_value.get.side_effect = (
            ClientError()
        )
        with (
            patch.object(file_store, "movies", movies),
            patch.object(file_store.config, "FS_BACKEND", "s3"),
        ):
            with pytest.raises(RequestedRangeNotSatisfiable):
                file_store.read_movie_range("lowdef", "1", "bytes=999-")
