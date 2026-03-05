from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class PlaylistRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode("E01")
        self.generate_fixture_sequence("SE01")
        self.generate_fixture_shot("SH01")
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_shot_task()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)

    def test_get_all_project_playlists(self):
        self.generate_fixture_playlist("Playlist 1")
        result = self.get(
            f"/data/projects/{self.project_id}/playlists/all"
        )
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_get_episode_playlists(self):
        self.generate_fixture_playlist(
            "Episode Playlist", episode_id=self.episode.id
        )
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode_id}/playlists"
        )
        self.assertIsInstance(result, list)

    def test_get_project_playlist(self):
        self.generate_fixture_playlist("Single Playlist")
        playlists = self.get(
            f"/data/projects/{self.project_id}/playlists"
        )
        playlist_id = playlists[0]["id"]
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/playlists/{playlist_id}"
        )
        self.assertEqual(result["id"], playlist_id)

    def test_get_entity_preview_files(self):
        result = self.get(
            f"/data/playlists/entities/{self.shot.id}/preview-files"
        )
        self.assertIsInstance(result, dict)

    def test_get_project_build_jobs(self):
        result = self.get(
            f"/data/projects/{self.project_id}/build-jobs"
        )
        self.assertIsInstance(result, list)

    def test_create_temp_playlist(self):
        result = self.post(
            f"/data/projects/{self.project_id}/playlists/temp",
            {"task_ids": [str(self.shot_task.id)]},
            200,
        )
        self.assertIsInstance(result, list)

    def test_add_entity_to_playlist(self):
        self.generate_fixture_playlist("Add Entity Playlist")
        playlists = self.get(
            f"/data/projects/{self.project_id}/playlists"
        )
        playlist_id = playlists[0]["id"]
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entity",
            {"entity_id": str(self.shot.id)},
            200,
        )
        self.assertIsNotNone(result)
        playlist = self.get(
            f"/data/projects/{self.project_id}"
            f"/playlists/{playlist_id}"
        )
        shot_ids = [
            s["entity_id"] for s in playlist.get("shots", [])
        ]
        self.assertIn(str(self.shot.id), shot_ids)
