import datetime
import gzip
import os
import tempfile
import unittest

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.organisation import Organisation
from zou.app.services import backup_service, persons_service
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
        with gzip.open(self.filename, "rb") as dump:
            self.assertEqual(dump.read(), b"CREATE TABLE a;\nINSERT 1;\n")

    def test_the_command_names_the_database_to_dump(self):
        _, popen = self.run_backup(["x\n"], 0)

        self.assertEqual(
            popen.call_args.args[0],
            ["pg_dump", "-h", "localhost", "-p", "5432", "-U", "zou", "zoudb"],
        )

    def test_password_is_passed_through_the_environment(self):
        # It must never reach the command line, where ps would expose it.
        _, popen = self.run_backup(["x\n"], 0)

        self.assertNotIn("secret", " ".join(popen.call_args.args[0]))
        self.assertEqual(popen.call_args.kwargs["env"]["PGPASSWORD"], "secret")

    def test_failed_dump_raises_instead_of_returning_a_name(self):
        # pg_dump can fail after writing part of its output. Returning the
        # file name would advertise a backup that cannot be restored, and
        # dump_database would upload it to the store and drop the local copy.
        with self.assertRaises(BackupFailedException):
            self.run_backup(["CREATE TABLE a;\n"], 1)


class UploadTestCase(ApiDBTestCase):
    """
    Base for the commands that push a local preview store to object
    storage. Only the decision of what to upload is checked: the store
    itself is mocked, since in a test run both ends are the same local
    backend.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

    def write_local(self, backend, key):
        """
        Put a file where the uploader expects to find it.
        """
        path = backend.path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"payload")
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def days_old(self, row, days):
        row.update(
            {
                "updated_at": datetime.datetime.now()
                - datetime.timedelta(days=days)
            }
        )
        return row


class StoreDbBackupTestCase(UploadTestCase):
    def test_store_db_backup(self):
        with mock.patch.object(backup_service.file_store, "add_file") as add:
            backup_service.store_db_backup("dump.sql.gz", "/tmp/dump.sql.gz")

        add.assert_called_once_with(
            "dbbackup", "dump.sql.gz", "/tmp/dump.sql.gz"
        )


class UploadPreviewTestCase(UploadTestCase):
    """
    A preview goes to one of three buckets depending on its extension, and
    a movie or a picture carries three generated variants alongside it.
    """

    def a_preview(self, extension, **kwargs):
        preview_file = self.generate_fixture_preview_file(**kwargs)
        preview_file.update({"extension": extension})
        return preview_file

    def upload_all(self, exists=False):
        """
        Run the uploader with every store call captured, and hand back the
        {bucket: [id]} map of what it pushed.
        """
        with mock.patch.multiple(
            backup_service.file_store,
            add_picture=mock.DEFAULT,
            add_movie=mock.DEFAULT,
            add_file=mock.DEFAULT,
            exists_picture=mock.DEFAULT,
            exists_movie=mock.DEFAULT,
            exists_file=mock.DEFAULT,
        ) as store:
            for name in ["exists_picture", "exists_movie", "exists_file"]:
                store[name].return_value = exists
            backup_service.upload_preview_files_to_storage()
            return {
                name: [call.args[0] for call in store[name].call_args_list]
                for name in ["add_picture", "add_movie", "add_file"]
            }

    def test_a_picture_goes_to_the_picture_store_with_its_variants(self):
        preview_file = self.a_preview("png")
        preview_id = str(preview_file.id)
        for prefix in ["thumbnails", "thumbnails-square", "original"]:
            self.write_local(
                backup_service.local_picture, f"{prefix}-{preview_id}"
            )
        self.write_local(
            backup_service.local_picture, f"previews-{preview_id}"
        )

        pushed = self.upload_all()

        self.assertEqual(
            sorted(pushed["add_picture"]),
            ["original", "previews", "thumbnails", "thumbnails-square"],
        )
        self.assertEqual(pushed["add_movie"], [])
        self.assertEqual(pushed["add_file"], [])

    def test_a_movie_goes_to_the_movie_store(self):
        preview_file = self.a_preview("mp4")
        preview_id = str(preview_file.id)
        self.write_local(backup_service.local_movie, f"previews-{preview_id}")
        self.write_local(
            backup_service.local_picture, f"thumbnails-{preview_id}"
        )

        pushed = self.upload_all()

        self.assertEqual(pushed["add_movie"], ["previews"])
        # The generated poster frames are pictures whatever the preview is.
        self.assertEqual(pushed["add_picture"], ["thumbnails"])

    def test_anything_else_goes_to_the_file_store(self):
        preview_file = self.a_preview("obj")
        preview_id = str(preview_file.id)
        self.write_local(backup_service.local_file, f"previews-{preview_id}")
        # A leftover on disk, from a preview that was a picture before: the
        # variants belong to movies and pictures, and are not looked for
        # here even when one happens to be there.
        self.write_local(
            backup_service.local_picture, f"thumbnails-{preview_id}"
        )

        pushed = self.upload_all()

        self.assertEqual(pushed["add_file"], ["previews"])
        self.assertEqual(pushed["add_picture"], [])

    def test_what_the_store_already_holds_is_not_pushed_again(self):
        preview_file = self.a_preview("png")
        preview_id = str(preview_file.id)
        self.write_local(
            backup_service.local_picture, f"thumbnails-{preview_id}"
        )
        self.write_local(
            backup_service.local_picture, f"previews-{preview_id}"
        )

        pushed = self.upload_all(exists=True)

        self.assertEqual(pushed["add_picture"], [])

    def test_a_preview_with_no_local_file_is_skipped(self):
        self.a_preview("png")

        pushed = self.upload_all()

        self.assertEqual(pushed["add_picture"], [])

    def test_the_upload_can_be_held_to_the_recent_previews(self):
        """
        The incremental run: only what changed in the window is pushed,
        which is what makes a nightly backup cheap.
        """
        recent = self.a_preview("png", name="recent")
        old = self.a_preview("png", name="old", revision=2)
        for preview_file in [recent, old]:
            self.write_local(
                backup_service.local_picture,
                f"previews-{preview_file.id!s}",
            )
        self.days_old(old, 10)

        with mock.patch.object(
            backup_service.file_store, "add_picture"
        ) as add, mock.patch.object(
            backup_service.file_store, "exists_picture", return_value=False
        ):
            backup_service.upload_preview_files_to_storage(days=2)

        self.assertEqual(
            [call.args[1] for call in add.call_args_list], [str(recent.id)]
        )


class UploadEntityThumbnailsTestCase(UploadTestCase):
    """
    Avatars, which hang off three unrelated models rather than off a
    preview.
    """

    def upload(self, days=None):
        with mock.patch.object(
            backup_service.file_store, "add_picture"
        ) as add:
            backup_service.upload_entity_thumbnails_to_storage(days=days)
        return [call.args[1] for call in add.call_args_list]

    def test_only_the_rows_carrying_an_avatar_are_pushed(self):
        self.project.update({"has_avatar": True})
        self.write_local(
            backup_service.local_picture, f"thumbnails-{self.project.id!s}"
        )
        self.person.update({"has_avatar": False})

        uploaded = self.upload()

        self.assertIn(str(self.project.id), uploaded)
        self.assertNotIn(str(self.person.id), uploaded)

    def test_the_three_models_are_walked(self):
        """
        A production, the studio itself and a person each keep their avatar
        on their own table.
        """
        organisation = persons_service.get_organisation()
        Organisation.get(organisation["id"]).update({"has_avatar": True})
        self.project.update({"has_avatar": True})
        self.person.update({"has_avatar": True})

        uploaded = self.upload()

        self.assertEqual(
            sorted(uploaded),
            sorted(
                [
                    str(self.project.id),
                    organisation["id"],
                    str(self.person.id),
                ]
            ),
        )

    def test_the_upload_can_be_held_to_the_recent_rows(self):
        self.project.update({"has_avatar": True})
        self.person.update({"has_avatar": True})
        self.days_old(self.person, 10)

        self.assertEqual(self.upload(days=2), [str(self.project.id)])
