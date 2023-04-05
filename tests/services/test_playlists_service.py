from tests.base import ApiDBTestCase

from zou.app.models.playlist import Playlist
from zou.app.services import playlists_service


class PlaylistsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project_standard()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.episode_2 = self.generate_fixture_episode("E02")
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.project_dict = self.sequence.serialize()

    def generate_fixture_preview_files(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.task = self.generate_fixture_shot_task()
        self.generate_fixture_preview_file(revision=1)
        self.generate_fixture_preview_file(revision=2)

    def generate_fixture_playlists(self):
        Playlist.create(
            name="Playlist 1",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode.id,
        )
        Playlist.create(
            name="Playlist 2", shots={}, project_id=self.project_standard.id
        )
        Playlist.create(
            name="Playlist 3",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode_2.id,
        )
        self.playlist = Playlist.create(
            name="Playlist 4",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode_2.id,
        )
        return self.playlist.serialize()

    def test_get_playlists_for_project(self):
        self.generate_fixture_playlists()
        playlists = playlists_service.all_playlists_for_project(
            self.project.id
        )
        self.assertEqual(len(playlists), 3)
        self.assertTrue(
            "Playlist 2"
            not in [
                playlists[0]["name"],
                playlists[1]["name"],
                playlists[2]["name"],
            ]
        )
        self.playlist.update({"for_client": True})
        playlists = playlists_service.all_playlists_for_project(
            self.project.id, True
        )
        self.assertEqual(len(playlists), 1)

    def test_get_playlist_for_episode(self):
        self.generate_fixture_playlists()
        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, self.episode_2.id
        )
        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0]["name"], "Playlist 4")
        self.playlist.update({"for_client": True})
        playlists = playlists_service.all_playlists_for_project(
            self.project.id, True
        )
        self.assertEqual(len(playlists), 1)

        self.generate_fixture_playlist("Test main pack", for_entity="asset")
        self.generate_fixture_playlist(
            "Test all playlist", for_entity="asset", is_for_all=True
        )
        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, "main"
        )
        self.assertEqual(len(playlists), 1)
        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, "all"
        )
        self.assertEqual(len(playlists), 1)

    def test_generate_temp_playlist(self):
        self.generate_fixture_preview_files()
        task_id = self.task.id
        task_type_id = str(self.task.task_type_id)
        shots = playlists_service.generate_temp_playlist([task_id])
        self.assertEqual(len(shots), 1)
        self.assertEqual(str(self.shot.id), shots[0]["id"])
        self.assertEqual(len(shots[0]["preview_files"][task_type_id]), 2)

    def test_generate_playlisted_entity_from_task(self):
        self.generate_fixture_preview_files()
        task_id = self.task.id
        task_type_id = str(self.task.task_type_id)
        shot = playlists_service.generate_playlisted_entity_from_task(task_id)
        self.assertEqual(str(self.shot.id), shot["id"])
        self.assertEqual(shot["parent_name"], "S01")
        self.assertEqual(len(shot["preview_files"][task_type_id]), 2)

        self.task = self.generate_fixture_task()
        task_id = self.task.id
        asset = playlists_service.generate_playlisted_entity_from_task(task_id)
        self.assertEqual(str(self.asset.id), asset["id"])
        self.assertEqual(asset["parent_name"], "Props")
        self.assertEqual(asset["preview_files"], {})

    def test_get_preview_files_for_task(self):
        self.generate_fixture_preview_files()
        task_id = self.task.id
        preview_files = playlists_service.get_preview_files_for_task(task_id)
        self.assertEqual(len(preview_files), 2)
        self.assertEqual(preview_files[0]["revision"], 2)

    def test_build_playlist_dict(self):
        playlist = Playlist.create(
            name="Playlist 1",
            shots={},
            project_id=self.project.id,
            episode_id=self.episode.id,
        )
        playlist_dict = playlists_service.build_playlist_dict(playlist)
        self.assertTrue("shots" not in playlist_dict)
        self.assertEqual(playlist_dict["for_entity"], "shot")
