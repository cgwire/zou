import os
import tempfile
import threading
import unittest
import uuid

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.preview_file_storage_state import (
    PreviewFileStorageState,
)
from zou.app.commands import (
    sync_files_service,
)
from zou.app.stores import file_store


class FileCallbackTestCase(ApiDBTestCase):
    """
    The listeners downloading what an event announced: a preview, a
    preview background, a thumbnail.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person_id = str(self.person.id)

    def test_a_thumbnail_event_carries_the_id_of_its_own_model(self):
        """
        person:set-thumbnail and its siblings are emitted with a
        <model>_id, never a preview_file_id: the thumbnail of a person is
        stored under the person id.
        """
        with mock.patch.object(
            sync_files_service, "download_thumbnail_from_another_instance"
        ) as download:
            sync_files_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id}
            )
        download.assert_called_once_with("person", self.person_id)

    def test_a_downloaded_thumbnail_is_announced_locally(self):
        captured = self.capture_events("person:set-thumbnail")
        with mock.patch.object(
            sync_files_service, "download_thumbnail_from_another_instance"
        ):
            sync_files_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id}
            )
        self.assertEqual(len(captured), 1)

    def test_a_downloaded_preview_is_announced_locally(self):
        captured = self.capture_events("preview-file:add-file")
        with mock.patch.object(
            sync_files_service, "download_preview_from_another_instance"
        ):
            sync_files_service.retrieve_preview_file(
                {"preview_file_id": str(uuid.uuid4())}
            )
        self.assertEqual(len(captured), 1)

    def test_a_downloaded_preview_background_is_announced_locally(self):
        captured = self.capture_events("preview-background-file:add-file")
        with mock.patch.object(
            sync_files_service,
            "download_preview_background_from_another_instance",
        ):
            sync_files_service.retrieve_preview_background_file(
                {"preview_background_file_id": str(uuid.uuid4())}
            )
        self.assertEqual(len(captured), 1)

    def test_a_file_event_this_instance_emitted_is_ignored(self):
        with mock.patch.object(
            sync_files_service, "download_preview_from_another_instance"
        ) as download_preview, mock.patch.object(
            sync_files_service,
            "download_preview_background_from_another_instance",
        ) as download_background, mock.patch.object(
            sync_files_service, "download_thumbnail_from_another_instance"
        ) as download_thumbnail:
            sync_files_service.retrieve_preview_file(
                {"preview_file_id": str(uuid.uuid4()), "sync": True}
            )
            sync_files_service.retrieve_preview_background_file(
                {
                    "preview_background_file_id": str(uuid.uuid4()),
                    "sync": True,
                }
            )
            sync_files_service.get_retrieve_thumbnail("person")(
                {"person_id": self.person_id, "sync": True}
            )
        download_background.assert_not_called()
        download_preview.assert_not_called()
        download_thumbnail.assert_not_called()


class DownloadFileTestCase(unittest.TestCase):
    """
    The local copy of a file read from the object storage.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.file_path = os.path.join(self.folder, "preview.mp4")

    def test_partial_file_removed_on_error(self):
        def failing_dl_func(prefix, preview_file_id):
            yield b"partial content"
            raise RuntimeError("stream interrupted")

        with open(self.file_path, "wb") as previous:
            previous.write(b"previous complete content")

        sync_files_service.download_file(
            self.file_path, "previews", failing_dl_func, "preview-id"
        )
        # The previous download is not truncated either.
        with open(self.file_path, "rb") as downloaded:
            self.assertEqual(downloaded.read(), b"previous complete content")
        self.assertEqual(os.listdir(self.folder), ["preview.mp4"])

    def test_successful_download_keeps_file(self):
        def dl_func(prefix, preview_file_id):
            yield b"full content"

        sync_files_service.download_file(
            self.file_path, "previews", dl_func, "preview-id"
        )
        with open(self.file_path, "rb") as downloaded:
            self.assertEqual(downloaded.read(), b"full content")


class DownloadFromAnotherInstanceTestCase(unittest.TestCase):
    """
    The transfer of one stored file from the source instance: download to a
    temporary path, hand it to the local store, clean up either way.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.file_path = os.path.join(self.folder, "thumbnail.png")
        self.saved = []
        self.errors = {}

    def save(self, prefix, id, file_path):
        self.saved.append((prefix, id, file_path))

    def download(self, exists=False, force=False, status_code=200, attemps=3):
        def fake_download(path, file_path, **kwargs):
            with open(file_path, "wb") as downloaded:
                downloaded.write(b"content")
            return mock.Mock(status_code=status_code)

        # A failed attempt waits half a second before the next one: the
        # waits are patched out.
        with mock.patch.object(
            sync_files_service.gazu.client,
            "download",
            side_effect=fake_download,
        ) as downloaded, mock.patch.object(sync_files_service.time, "sleep"):
            sync_files_service.download_file_from_another_instance(
                "/pictures/thumbnails/persons/id.png",
                self.file_path,
                lambda prefix, id: exists,
                self.save,
                "thumbnails",
                "person-id",
                number_attemps=attemps,
                force=force,
                dict_errors=self.errors,
            )
        return downloaded

    def test_a_downloaded_file_reaches_the_store(self):
        self.download()
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(self.saved[0][0], "thumbnails")

    def test_the_temporary_file_does_not_survive_the_transfer(self):
        self.download()
        self.assertFalse(os.path.exists(self.file_path))

    def test_a_file_already_in_the_store_is_not_downloaded_again(self):
        downloaded = self.download(exists=True)
        downloaded.assert_not_called()
        self.assertEqual(self.saved, [])

    def test_a_resync_downloads_it_anyway(self):
        downloaded = self.download(exists=True, force=True)
        self.assertEqual(downloaded.call_count, 1)

    def test_a_failed_download_is_retried(self):
        downloaded = self.download(status_code=500, attemps=3)
        self.assertEqual(downloaded.call_count, 3)
        self.assertIn("person-id", self.errors["thumbnails"])

    def test_a_file_the_source_does_not_have_is_not_an_error(self):
        """
        A 404 means the row exists without its file on the source side.
        Reporting it would drown the errors that need an operator.
        """
        self.download(status_code=404)
        self.assertEqual(self.errors, {})

    def test_does_not_wait_for_a_file_still_processing_on_the_source(self):
        """
        A sync has no reason to wait for a remote file to finish building:
        it should fail (and retry the outer loop) right away rather than
        inherit gazu's default processing budget.
        """
        downloaded = self.download()
        self.assertEqual(
            downloaded.call_args.kwargs.get("processing_timeout"), 0
        )


class MultithreadErrorsTestCase(unittest.TestCase):
    """
    The error report the file sync fills from its worker pool.
    """

    def test_the_errors_are_nested_by_prefix(self):
        errors = {}
        sync_files_service.write_multithread_dict_errors(
            errors, "previews", "id-1", "boom"
        )
        sync_files_service.write_multithread_dict_errors(
            errors, "previews", "id-2", "bang"
        )
        sync_files_service.write_multithread_dict_errors(
            errors, "thumbnails", "id-1", "thud"
        )
        self.assertEqual(
            errors,
            {
                "previews": {"id-1": "boom", "id-2": "bang"},
                "thumbnails": {"id-1": "thud"},
            },
        )

    def test_nothing_is_lost_under_threads(self):
        """
        The function exists to be called from a worker pool, so the point is
        that concurrent writers do not drop each other's entries.
        """
        errors = {}

        def write(index):
            sync_files_service.write_multithread_dict_errors(
                errors, "previews", f"id-{index}", index
            )

        threads = [
            threading.Thread(target=write, args=(index,))
            for index in range(50)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(len(errors["previews"]), 50)


class SyncSourceMovieTestCase(ApiDBTestCase):
    """
    Which movie prefixes are pulled from the other instance.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file()

    def fetched_paths(self, sync_source_movie_files):
        with mock.patch.object(
            sync_files_service.config,
            "SYNC_SOURCE_MOVIE_FILES",
            sync_source_movie_files,
        ), mock.patch.object(
            sync_files_service, "download_file_from_another_instance"
        ) as download:
            sync_files_service.download_preview_from_another_instance(
                self.preview_file
            )
        return [call.args[0] for call in download.mock_calls]

    def test_the_source_movie_is_left_out_by_default(self):
        paths = self.fetched_paths(False)
        self.assertIn(
            f"/movies/originals/preview-files/{self.preview_file.id}.mp4",
            paths,
        )
        self.assertNotIn(
            f"/movies/source/preview-files/{self.preview_file.id}.mp4",
            paths,
        )

    def test_the_source_movie_is_pulled_when_asked_for(self):
        """
        An instance skipping the normalization stores its movie under the
        source prefix: without it the copy would hold no movie at all.
        """
        paths = self.fetched_paths(True)
        self.assertIn(
            f"/movies/source/preview-files/{self.preview_file.id}.mp4",
            paths,
        )


class RecordSyncedPreviewStatesTestCase(ApiDBTestCase):
    """
    download_preview_from_another_instance runs in a ThreadPool worker
    when the sync is multithreaded (download_files_from_another_instance
    with multithreaded=True), which carries no Flask app context.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.preview_file = self.generate_fixture_preview_file()
        self.preview_file_id = str(self.preview_file.id)

    def test_records_states_when_called_without_an_app_context(self):
        errors = []

        def run():
            try:
                with mock.patch.object(
                    file_store, "exists_confirmed", return_value=True
                ):
                    sync_files_service._record_synced_preview_states(
                        self.preview_file_id, "mp4"
                    )
            except Exception as e:
                errors.append(e)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertGreater(
            PreviewFileStorageState.query.filter_by(
                preview_file_id=self.preview_file_id
            ).count(),
            0,
        )
