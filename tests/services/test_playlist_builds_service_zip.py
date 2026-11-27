import os

from tests.base import ApiDBTestCase
from zou.app.services import playlist_builds_service


class PlaylistZipBuildTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_episode("E01")
        self.project_id = str(self.project.id)
        self.serialized_episode = self.episode.serialize(obj_type="Episode")
        self.episode_id = str(self.episode.id)

        self.generate_fixture_sequence("SE01")
        self.serialized_sequence = self.sequence.serialize(obj_type="Sequence")

        self.generate_fixture_shot("SE01")
        self.generate_fixture_shot("SE02")
        self.generate_fixture_shot("SE03")

    def tearDown(self):
        super().tearDown()
        self.delete_test_folder()

    def test_concurrent_zip_builds_keep_their_own_file(self):
        # Two downloads of the same playlist: the second build must not
        # remove the archive the first one is about to send.
        playlist = self.generate_fixture_playlist("Playlist 1")
        first_path = playlist_builds_service.build_playlist_zip_file(playlist)
        second_path = playlist_builds_service.build_playlist_zip_file(playlist)
        try:
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(os.path.exists(first_path))
        finally:
            for path in (first_path, second_path):
                if os.path.exists(path):
                    os.remove(path)
