from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class PlaylistTestCase(ApiDBTestCase):

    def setUp(self):
        super(PlaylistTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
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
        super(PlaylistTestCase, self).tearDown()
        self.delete_test_folder()

    def test_get_playlists(self):
        self.generate_fixture_playlist("Playlist 1")
        playlists = self.get("data/projects/%s/playlists" % self.project_id)
        self.assertEqual(len(playlists), 1)

    def test_delete_playlist(self):
        self.generate_fixture_playlist("Playlist 1")
        playlists = self.get("data/projects/%s/playlists" % self.project_id)
        self.delete("data/playlists/%s" % playlists[0]["id"])
        playlists = self.get("data/projects/%s/playlists" % self.project_id)
        self.assertEqual(len(playlists), 0)

    def test_download_playlist(self):
        self.generate_fixture_playlist("Playlist 1", for_client=False)
        result_file_path = self.get_file_path("playlist.zip")
        url_path = "/data/playlists/%s/download/zip" % self.playlist.id
        self.create_test_folder()
        self.download_file(url_path, result_file_path)

        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()
        self.download_file(url_path, result_file_path, 403)
        self.generate_fixture_playlist("Playlist 2", for_client=True)
        url_path = "/data/playlists/%s/download/zip" % self.playlist.id
        self.download_file(url_path, result_file_path)
