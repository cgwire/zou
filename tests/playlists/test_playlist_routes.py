from tests.base import ApiDBTestCase

from zou.app.models.playlist import Playlist
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
        result = self.get(f"/data/projects/{self.project_id}/playlists/all")
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
        playlists = self.get(f"/data/projects/{self.project_id}/playlists")
        playlist_id = playlists[0]["id"]
        result = self.get(
            f"/data/projects/{self.project_id}" f"/playlists/{playlist_id}"
        )
        self.assertEqual(result["id"], playlist_id)

    def test_get_entity_preview_files(self):
        result = self.get(
            f"/data/playlists/entities/{self.shot.id}/preview-files"
        )
        self.assertIsInstance(result, dict)

    def test_get_project_build_jobs(self):
        result = self.get(f"/data/projects/{self.project_id}/build-jobs")
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
        playlists = self.get(f"/data/projects/{self.project_id}/playlists")
        playlist_id = playlists[0]["id"]
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entity",
            {"entity_id": str(self.shot.id)},
            200,
        )
        self.assertIsNotNone(result)
        playlist = self.get(
            f"/data/projects/{self.project_id}" f"/playlists/{playlist_id}"
        )
        shot_ids = [s["entity_id"] for s in playlist.get("shots", [])]
        self.assertIn(str(self.shot.id), shot_ids)

    def _create_playlist(self, name, creator_id=None):
        return Playlist.create(
            name=name,
            project_id=self.project.id,
            for_entity="shot",
            is_for_all=False,
            for_client=False,
            shots=[],
            created_by=creator_id,
        ).serialize()

    def test_add_entity_as_supervisor_creator(self):
        self.generate_fixture_user_supervisor()
        playlist = self._create_playlist(
            "Supervisor Playlist", creator_id=self.user_supervisor["id"]
        )
        self.log_in_supervisor()
        self.post(
            f"/actions/playlists/{playlist['id']}/add-entity",
            {"entity_id": str(self.shot.id)},
            200,
        )

    def test_add_entity_as_supervisor_non_creator_is_forbidden(self):
        self.generate_fixture_user_supervisor()
        self.generate_fixture_user_supervisor_2()
        playlist = self._create_playlist(
            "Other Supervisor Playlist",
            creator_id=self.user_supervisor_2["id"],
        )
        self.log_in_supervisor()
        self.post(
            f"/actions/playlists/{playlist['id']}/add-entity",
            {"entity_id": str(self.shot.id)},
            403,
        )

    def test_add_entity_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        playlist = self._create_playlist(
            "Artist Playlist", creator_id=self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        self.post(
            f"/actions/playlists/{playlist['id']}/add-entity",
            {"entity_id": str(self.shot.id)},
            403,
        )

    def test_update_playlist_as_supervisor_creator(self):
        self.generate_fixture_user_supervisor()
        playlist = self._create_playlist(
            "Supervisor Playlist", creator_id=self.user_supervisor["id"]
        )
        self.log_in_supervisor()
        self.put(
            f"/data/playlists/{playlist['id']}",
            {"name": "Renamed by supervisor"},
            200,
        )

    def test_update_playlist_as_supervisor_non_creator_is_forbidden(self):
        self.generate_fixture_user_supervisor()
        self.generate_fixture_user_supervisor_2()
        playlist = self._create_playlist(
            "Other Playlist", creator_id=self.user_supervisor_2["id"]
        )
        self.log_in_supervisor()
        self.put(
            f"/data/playlists/{playlist['id']}",
            {"name": "Should fail"},
            403,
        )

    def test_delete_playlist_as_supervisor_creator(self):
        self.generate_fixture_user_supervisor()
        playlist = self._create_playlist(
            "Supervisor Playlist", creator_id=self.user_supervisor["id"]
        )
        self.log_in_supervisor()
        self.delete(f"/data/playlists/{playlist['id']}")
