import gzip
import os
import tempfile
import unittest

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.services import backup_service
from zou.app.services.exception import BackupFailedException


class FakeStdout:
    """
    Feed the given lines then the empty string that ends the read loop.
    """

    def __init__(self, lines):
        self.lines = iter(lines + [""])
        self.closed = False

    def readline(self):
        return next(self.lines)

    def close(self):
        self.closed = True


class FakePopen:
    """
    Stand in for the pg_dump process.
    """

    def __init__(self, lines, returncode):
        self.stdout = FakeStdout(lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode


class GenerateDbBackupTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.filename = tempfile.mkstemp(suffix=".sql.gz")
        os.close(fd)
        self.addCleanup(
            lambda: os.path.exists(self.filename) and os.remove(self.filename)
        )

    def run_backup(self, lines, returncode):
        fake = FakePopen(lines, returncode)
        with mock.patch.object(
            backup_service.subprocess, "Popen", return_value=fake
        ) as popen:
            result = backup_service.generate_db_backup(
                "localhost", "5432", "zou", "secret", "zoudb", self.filename
            )
        return result, popen

    def test_dump_is_written_gzipped(self):
        result, _ = self.run_backup(["CREATE TABLE a;\n", "INSERT 1;\n"], 0)
        self.assertEqual(result, self.filename)
        with gzip.open(self.filename, "rb") as f:
            self.assertEqual(f.read(), b"CREATE TABLE a;\nINSERT 1;\n")

    def test_password_is_passed_through_the_environment(self):
        # It must never reach the command line, where ps would expose it.
        _, popen = self.run_backup(["x\n"], 0)
        args, kwargs = popen.call_args
        self.assertNotIn("secret", " ".join(args[0]))
        self.assertEqual(kwargs["env"]["PGPASSWORD"], "secret")

    def test_failed_dump_raises_instead_of_returning_a_name(self):
        # pg_dump can fail after writing part of its output. Returning the
        # file name would advertise a backup that cannot be restored, and
        # dump_database would upload it to the store and drop the local copy.
        with self.assertRaises(BackupFailedException):
            self.run_backup(["CREATE TABLE a;\n"], 1)


class UploadToStorageTestCase(ApiDBTestCase):
    """
    The commands that push a local preview store to object storage. Only the
    decision of what to upload is checked here: the store itself is mocked,
    since in a test run both ends are the same local backend.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_task()

    def write_local_picture(self, key):
        path = backup_service.local_picture.path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as picture:
            picture.write(b"png")
        return path

    def test_store_db_backup(self):
        with mock.patch.object(backup_service.file_store, "add_file") as add:
            backup_service.store_db_backup("dump.sql.gz", "/tmp/dump.sql.gz")
        add.assert_called_once_with(
            "dbbackup", "dump.sql.gz", "/tmp/dump.sql.gz"
        )

    def test_upload_entity_thumbnails_to_storage(self):
        self.project.update({"has_avatar": True})
        self.write_local_picture(f"thumbnails-{self.project.id}")
        self.person.update({"has_avatar": False})

        with mock.patch.object(
            backup_service.file_store, "add_picture"
        ) as add:
            backup_service.upload_entity_thumbnails_to_storage()

        uploaded = {call.args[1] for call in add.call_args_list}
        self.assertIn(str(self.project.id), uploaded)
        self.assertNotIn(str(self.person.id), uploaded)

    def test_upload_preview_files_to_storage(self):
        preview_file = self.generate_fixture_preview_file()
        preview_file_id = str(preview_file.id)
        self.write_local_picture(f"thumbnails-{preview_file_id}")

        with mock.patch.object(
            backup_service.file_store, "add_picture"
        ) as add, mock.patch.object(
            backup_service.file_store, "exists_picture", return_value=False
        ):
            backup_service.upload_preview_files_to_storage()

        add.assert_called_once_with(
            "thumbnails",
            preview_file_id,
            backup_service.local_picture.path(f"thumbnails-{preview_file_id}"),
        )
