from tests.base import ApiDBTestCase


class PlaylistCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistCsvExportTestCase, self).setUp()
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
        self.generate_fixture_playlist("Playlist 1")

    def test_get_playlist(self):
        csv_playlist = self.get_raw(
            "/export/csv/playlists/%s" % self.playlist.id
        )
        expected_result = "Playlist;Cosmos Landromat | for shots;Playlist 1;"
        self.assertTrue(csv_playlist.startswith(expected_result))
