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
