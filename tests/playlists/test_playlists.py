from unittest.mock import ANY

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

    def test_get_playlist(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        task_type_id = self.task_type.id
        shot_id = self.shot.id
        playlist = self.generate_fixture_playlist(
            "Playlist",
            shots=[self.shot.serialize()],
            task_type_id=task_type_id,
        )
        playlist_id = playlist["id"]
        self.generate_fixture_task(
            name="Shot task",
            entity_id=shot_id,
            task_type_id=task_type_id,
        )
        preview_file = self.generate_fixture_preview_file()
        preview_file_id = preview_file.id
        response = self.get(
            "/data/projects/%s/playlists/%s" % (self.project_id, playlist_id)
        )
        self.assertEqual(
            response,
            {
                "build_jobs": [],
                "created_at": ANY,
                "episode_id": None,
                "for_client": False,
                "for_entity": "shot",
                "id": playlist["id"],
                "is_for_all": False,
                "name": "Playlist",
                "project_id": ANY,
                "shots": [
                    {
                        "canceled": False,
                        "code": None,
                        "created_at": ANY,
                        "data": {"fps": 25, "frame_in": 0, "frame_out": 100},
                        "description": "Description Shot 01",
                        "entity_type_id": ANY,
                        "id": str(shot_id),
                        "name": "SE03",
                        "nb_entities_out": 0,
                        "nb_frames": 0,
                        "parent_id": ANY,
                        "preview_file_id": None,
                        "preview_files": {
                            str(task_type_id): [
                                {
                                    "annotations": None,
                                    "created_at": ANY,
                                    "extension": "mp4",
                                    "id": str(preview_file_id),
                                    "revision": 1,
                                    "status": "ready",
                                    "task_id": ANY,
                                }
                            ]
                        },
                        "project_id": ANY,
                        "ready_for": None,
                        "shotgun_id": None,
                        "source_id": None,
                        "type": "Entity",
                        "updated_at": ANY,
                    }
                ],
                "task_type_id": str(task_type_id),
                "type": "Playlist",
                "updated_at": ANY,
            },
        )

    def test_get_playlists(self):
        self.generate_fixture_playlist("Playlist 1")
        playlists = self.get("data/projects/%s/playlists" % self.project_id)
        self.assertEqual(len(playlists), 1)

    def test_get_playlists_by_task_type(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_playlist(
            "Playlist 1", task_type_id=self.task_type_layout.id
        )
        self.generate_fixture_playlist(
            "Playlist 2", task_type_id=self.task_type_animation.id
        )
        self.generate_fixture_playlist(
            "Playlist 3", task_type_id=self.task_type_animation.id
        )
        playlists = self.get(
            "data/projects/%s/playlists?task_type_id=%s"
            % (self.project_id, self.task_type_animation.id)
        )
        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0]["name"], "Playlist 3")
        self.assertEqual(playlists[1]["name"], "Playlist 2")

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
