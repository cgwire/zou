import os
import tempfile

from types import SimpleNamespace
from unittest import mock

from tests.base import ApiDBTestCase

from zou.app import config, db
from zou.app.models.department import Department
from zou.app.models.stored_file import StoredFile
from zou.app.services import (
    deletion_service,
    playlists_service,
    preview_files_service,
    stored_files_service,
)
from zou.app.stores import file_store
from zou.app.exceptions import PreviewProcessingFailedException
from zou.app.utils import fields


class StoredFilesServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.file_id = str(fields.gen_uuid())
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"stored file content")
            self.tmp_path = tmp.name
        self.addCleanup(os.remove, self.tmp_path)
        # The registry commits on a connection of its own, out of the
        # test transaction: its rows outlive the test.
        self.addCleanup(self.clear_registry)

    def clear_registry(self):
        with db.engine.begin() as connection:
            connection.execute(StoredFile.__table__.delete())

    def get_row(self, prefix="thumbnails", file_id=None):
        return StoredFile.get_by(
            bucket="pictures",
            key=file_store.make_key(prefix, file_id or self.file_id),
        )

    def add_picture(self, prefix="thumbnails", file_id=None):
        file_store.add_picture(prefix, file_id or self.file_id, self.tmp_path)

    def ops(self, row):
        return [entry["op"] for entry in row.journal]

    def test_write_is_recorded(self):
        self.add_picture()
        row = self.get_row()
        self.assertEqual(row.prefix, "thumbnails")
        self.assertEqual(row.file_id, self.file_id)
        self.assertEqual(row.size, os.path.getsize(self.tmp_path))
        self.assertIsNone(row.deleted_at)
        self.assertEqual(self.ops(row), ["create"])

    def test_rewrite_is_recorded_as_update(self):
        self.add_picture()
        self.add_picture()
        self.assertEqual(self.ops(self.get_row()), ["create", "update"])

    def test_copy_records_the_target(self):
        self.add_picture()
        target_id = str(fields.gen_uuid())
        file_store.copy_picture(
            "thumbnails", self.file_id, "thumbnails", target_id
        )
        self.assertEqual(self.ops(self.get_row(file_id=target_id)), ["create"])

    def test_delete_only_marks_without_remove_files(self):
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        row = self.get_row()
        self.assertIsNotNone(row.deleted_at)
        self.assertIsNone(row.purged_at)
        self.assertFalse(row.purge_forced)
        self.assertTrue(file_store.exists_picture("thumbnails", self.file_id))

    def test_forced_delete_removes_local_file_right_away(self):
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id, force=True)
        row = self.get_row()
        self.assertIsNotNone(row.deleted_at)
        self.assertIsNotNone(row.purged_at)
        self.assertEqual(self.ops(row), ["create", "delete", "purge"])
        self.assertFalse(file_store.exists_picture("thumbnails", self.file_id))

    def test_delete_of_unknown_file_creates_the_row(self):
        file_store.remove_picture("thumbnails", self.file_id)
        row = self.get_row()
        self.assertIsNotNone(row.deleted_at)
        self.assertEqual(self.ops(row), ["delete"])

    def test_delete_with_remove_files_removes_right_away(self):
        self.add_picture()
        with mock.patch.object(config, "REMOVE_FILES", True):
            file_store.remove_picture("thumbnails", self.file_id)
        row = self.get_row()
        self.assertIsNotNone(row.purged_at)
        self.assertFalse(file_store.exists_picture("thumbnails", self.file_id))

    def test_delete_without_registry_still_removes(self):
        self.add_picture()
        with mock.patch.object(
            stored_files_service, "_session", side_effect=RuntimeError("db")
        ):
            file_store.remove_picture("thumbnails", self.file_id, force=True)
        self.assertFalse(file_store.exists_picture("thumbnails", self.file_id))

    def test_write_after_delete_revives_the_file(self):
        # An avatar removed then uploaded again keeps its key: the purge
        # must not remove the new file.
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        self.add_picture()
        row = self.get_row()
        self.assertIsNone(row.deleted_at)
        self.assertEqual(self.ops(row), ["create", "delete", "undelete"])
        self.assertEqual(stored_files_service.get_files_to_purge(), [])

    def test_files_to_purge_follow_remove_files(self):
        forced_id = str(fields.gen_uuid())
        file_store.remove_picture("thumbnails", self.file_id)
        stored_files_service.mark_deleted(
            [("pictures", "thumbnails", forced_id)], force=True
        )

        to_purge = stored_files_service.get_files_to_purge()
        self.assertEqual([row["file_id"] for row in to_purge], [forced_id])

        with mock.patch.object(config, "REMOVE_FILES", True):
            to_purge = stored_files_service.get_files_to_purge()
        self.assertEqual(
            {row["file_id"] for row in to_purge}, {self.file_id, forced_id}
        )
        self.assertEqual(
            stored_files_service.get_files_to_purge(grace_delay=3600), []
        )

    def test_purge(self):
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        with mock.patch.object(config, "REMOVE_FILES", True):
            self.assertTrue(
                file_store.purge("pictures", "thumbnails", self.file_id)
            )
        self.assertIsNotNone(self.get_row().purged_at)
        self.assertFalse(file_store.exists_picture("thumbnails", self.file_id))
        self.assertEqual(stored_files_service.get_files_to_purge(), [])

    def test_purge_of_a_missing_file_counts_as_purged(self):
        file_store.remove_picture("thumbnails", self.file_id, force=True)
        self.assertIsNotNone(self.get_row().purged_at)

    def test_purge_needs_remove_files_or_force(self):
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        self.assertFalse(
            file_store.purge("pictures", "thumbnails", self.file_id)
        )
        self.assertIsNone(self.get_row().purged_at)
        self.assertTrue(file_store.exists_picture("thumbnails", self.file_id))

    def test_purge_leaves_a_revived_file_alone(self):
        # The purge job read the row as marked, the file was uploaded
        # again before it ran: the check under the lock must see it.
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        self.add_picture()
        with mock.patch.object(config, "REMOVE_FILES", True):
            self.assertFalse(
                file_store.purge("pictures", "thumbnails", self.file_id)
            )
        self.assertIsNone(self.get_row().deleted_at)
        self.assertTrue(file_store.exists_picture("thumbnails", self.file_id))

    def test_write_is_recorded_before_the_object(self):
        # Reviving the row first is what keeps a concurrent purge from
        # removing the new object.
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        seen = []
        record_write = stored_files_service.record_write

        def spy(*args, **kwargs):
            seen.append(file_store.exists_picture("thumbnails", self.file_id))
            return record_write(*args, **kwargs)

        os.remove(
            file_store.get_local_picture_path("thumbnails", self.file_id)
        )
        with mock.patch.object(stored_files_service, "record_write", spy):
            self.add_picture()
        self.assertEqual(seen, [False])

    def test_local_preview_copy_revives_the_target(self):
        # The local backend copies previews with shutil, outside of the
        # file store: the target key must be revived all the same.
        target_id = str(fields.gen_uuid())
        self.add_picture()
        self.add_picture(file_id=target_id)
        file_store.remove_picture("thumbnails", target_id)
        copied = preview_files_service.copy_preview_file_on_storage(
            "pictures",
            file_store.get_local_picture_path,
            file_store.exists_picture,
            file_store.copy_picture,
            "thumbnails",
            self.file_id,
            target_id,
        )
        self.assertTrue(copied)
        self.assertIsNone(self.get_row(file_id=target_id).deleted_at)
        with mock.patch.object(config, "REMOVE_FILES", True):
            self.assertFalse(
                file_store.purge("pictures", "thumbnails", target_id)
            )
        self.assertTrue(file_store.exists_picture("thumbnails", target_id))

    def test_failed_purge_is_recorded(self):
        self.add_picture()
        file_store.remove_picture("thumbnails", self.file_id)
        with mock.patch.object(
            file_store, "_delete_exact", side_effect=RuntimeError("down")
        ), mock.patch.object(config, "REMOVE_FILES", True):
            self.assertFalse(
                file_store.purge("pictures", "thumbnails", self.file_id)
            )
        row = self.get_row()
        self.assertIsNone(row.purged_at)
        self.assertEqual(row.purge_attempts, 1)
        self.assertEqual(row.last_error, "down")
        self.assertEqual(self.ops(row)[-1], "purge_failed")

    def test_journal_is_capped(self):
        for _ in range(stored_files_service.JOURNAL_MAX_LENGTH + 5):
            self.add_picture()
        row = self.get_row()
        self.assertEqual(
            len(row.journal), stored_files_service.JOURNAL_MAX_LENGTH
        )
        self.assertEqual(self.ops(row)[-1], "update")

    def test_registry_failure_does_not_fail_the_upload(self):
        with mock.patch.object(
            stored_files_service, "insert", side_effect=RuntimeError("db")
        ):
            self.add_picture()
        self.assertTrue(file_store.exists_picture("thumbnails", self.file_id))

    def test_registry_failure_keeps_caller_changes(self):
        department = Department(name="Registry", color="#000000")
        db.session.add(department)
        db.session.flush()
        with mock.patch.object(
            stored_files_service, "insert", side_effect=RuntimeError("db")
        ):
            self.add_picture()
        self.assertIsNotNone(Department.get(department.id))

    def test_remove_preview_file_marks_its_files(self):
        self.generate_fixture_preview_file()
        preview_file_id = str(self.preview_file.id)
        self.add_picture(file_id=preview_file_id)

        deletion_service.remove_preview_file_by_id(preview_file_id)

        row = self.get_row(file_id=preview_file_id)
        self.assertIsNotNone(row.deleted_at)
        self.assertTrue(
            file_store.exists_picture("thumbnails", preview_file_id)
        )
        marked = {
            (stored_file.bucket, stored_file.prefix)
            for stored_file in StoredFile.query.filter_by(
                file_id=preview_file_id
            )
        }
        self.assertIn(("movies", "previews"), marked)
        self.assertIn(("pictures", "tiles"), marked)

    def test_preview_deletion_takes_two_transactions(self):
        # One to mark every file of the movie, one to purge them all.
        self.generate_fixture_preview_file()
        with mock.patch.object(
            stored_files_service,
            "_session",
            wraps=stored_files_service._session,
        ) as session:
            deletion_service.remove_preview_file_by_id(
                str(self.preview_file.id), force=True
            )
        self.assertEqual(session.call_count, 2)
        rows = StoredFile.query.filter_by(
            file_id=str(self.preview_file.id)
        ).all()
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(row.purged_at is not None for row in rows))

    def test_remote_normalize_records_before_the_job(self):
        # A job failing halfway may have written some files already.
        with mock.patch.object(
            preview_files_service,
            "_run_remote_normalize_movie",
            return_value="encoding failed",
        ):
            with self.assertRaises(PreviewProcessingFailedException):
                preview_files_service._encode_on_remote_worker(
                    self.file_id,
                    "movie.mp4",
                    25,
                    1920,
                    1080,
                    {},
                    True,
                    False,
                    [],
                )
        recorded = {
            (row.bucket, row.prefix)
            for row in StoredFile.query.filter_by(file_id=self.file_id)
        }
        self.assertIn(("movies", "previews"), recorded)
        self.assertIn(("movies", "lowdef"), recorded)
        self.assertIn(("pictures", "tiles"), recorded)

    def test_remote_playlist_records_before_the_job(self):
        with mock.patch.object(
            playlists_service.remote_job,
            "run_job",
            side_effect=RuntimeError("job failed"),
        ), mock.patch.object(
            playlists_service.config_store,
            "get_nomad_playlist_job",
            return_value="zou-playlist",
        ):
            with self.assertRaises(RuntimeError):
                playlists_service._run_remote_job_build_playlist(
                    None,
                    {"id": self.file_id},
                    [],
                    SimpleNamespace(width=1920, height=1080, fps=25),
                    "playlist.mp4",
                    False,
                )
        row = StoredFile.get_by(
            bucket="movies", key=file_store.make_key("playlists", self.file_id)
        )
        self.assertIsNotNone(row)

    def test_remote_tile_records_before_the_job(self):
        self.generate_fixture_preview_file()
        with mock.patch.object(
            preview_files_service.remote_job,
            "run_job",
            side_effect=RuntimeError("job failed"),
        ), mock.patch.object(
            preview_files_service.config_store,
            "get_nomad_tile_job",
            return_value="zou-tile",
        ):
            with self.assertRaises(RuntimeError):
                preview_files_service._run_remote_tile_job(
                    None, self.preview_file
                )
        self.assertIsNotNone(
            self.get_row(prefix="tiles", file_id=str(self.preview_file.id))
        )
