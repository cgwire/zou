from tests.base import ApiDBTestCase


class PlaylistCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_episode("E01")
        self.generate_fixture_sequence("SE01")
        self.generate_fixture_shot("SH01")
        self.generate_fixture_shot_task()
        self.generate_fixture_preview_file(task_id=self.shot_task.id)
        self.generate_fixture_playlist("Playlist 1")
        self.playlist.update(
            {
                "shots": [
                    {
                        "entity_id": str(self.shot.id),
                        "preview_file_id": str(self.preview_file.id),
                    }
                ]
            }
        )

    def test_get_playlist(self):
        csv_playlist = self.get_raw(
            f"/export/csv/playlists/{self.playlist.id}"
        )
        expected_result = "Playlist;Cosmos Landromat | for shots;Playlist 1;"
        self.assertTrue(csv_playlist.startswith(expected_result))
        row = csv_playlist.splitlines()[-1].split(";")
        self.assertEqual(row[0], "E01 / SE01 / SH01")
        self.assertEqual(row[2], self.task_type_animation.name)
        self.assertEqual(row[4], "1")
