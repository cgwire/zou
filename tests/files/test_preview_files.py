from tests.base import ApiDBTestCase


class PreviewFilesTestCase(ApiDBTestCase):
    def setUp(self):
        super(PreviewFilesTestCase, self).setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()

    def test_get_running_preview_filless(self):
        self.generate_fixture_preview_file().serialize()
        preview_file_broken = self.generate_fixture_preview_file(
            revision=2, status="broken"
        ).serialize()
        preview_file_processing = self.generate_fixture_preview_file(
            revision=3, status="processing"
        ).serialize()
        preview_files = self.get("data/playlists/preview-files/running")
        self.assertEqual(len(preview_files), 2)
        self.assertEqual(preview_files[0]["id"], preview_file_processing["id"])
        self.assertEqual(preview_files[1]["id"], preview_file_broken["id"])
