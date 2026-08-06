from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.build_job import BuildJob
from zou.app.models.playlist import Playlist
from zou.app.services import (
    playlists_service,
    entities_service,
    projects_service,
)


class PlaylistsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project_standard()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.episode_2 = self.generate_fixture_episode("E02")
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()

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

    def test_all_playlists_for_project_is_scoped_to_its_production(self):
        self.generate_fixture_playlists()

        playlists = playlists_service.all_playlists_for_project(
            self.project.id
        )

        self.assertEqual(
            sorted(playlist["name"] for playlist in playlists),
            ["Playlist 1", "Playlist 3", "Playlist 4"],
        )

    def test_all_playlists_for_project_holds_the_ones_for_clients(self):
        self.generate_fixture_playlists()
        self.playlist.update({"for_client": True})

        playlists = playlists_service.all_playlists_for_project(
            self.project.id, True
        )

        self.assertEqual(
            [playlist["name"] for playlist in playlists], ["Playlist 4"]
        )

    def test_all_playlists_for_episode(self):
        self.generate_fixture_playlists()

        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, self.episode_2.id
        )

        self.assertEqual(
            sorted(playlist["name"] for playlist in playlists),
            ["Playlist 3", "Playlist 4"],
        )

    def test_all_playlists_for_episode_is_scoped_to_its_production(self):
        # An episode belongs to one production, but the caller names both
        # and the pair has to agree.
        self.generate_fixture_playlists()
        elsewhere = Playlist.create(
            name="Elsewhere",
            shots={},
            project_id=self.project_standard.id,
            episode_id=self.episode_2.id,
        )

        playlists = playlists_service.all_playlists_for_episode(
            self.project_standard.id, self.episode_2.id
        )

        self.assertEqual(
            [playlist["name"] for playlist in playlists], [elsewhere.name]
        )

    def test_the_main_pack_holds_what_belongs_to_no_episode(self):
        self.generate_fixture_playlists()
        self.generate_fixture_playlist("Test main pack", for_entity="asset")
        self.generate_fixture_playlist(
            "Test all playlist", for_entity="asset", is_for_all=True
        )

        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, "main"
        )

        self.assertEqual(
            [playlist["name"] for playlist in playlists], ["Test main pack"]
        )

    def test_the_main_pack_holds_the_playlists_that_predate_the_flag(self):
        """
        is_for_all was added to an existing table, nullable and without a
        server default: every playlist made before that migration carries
        null rather than false, and belongs in the main pack.
        """
        older = self.generate_fixture_playlist(
            "Older than the flag", for_entity="asset"
        )
        db.session.execute(
            db.text("UPDATE playlist SET is_for_all = NULL WHERE id = :id"),
            {"id": older["id"]},
        )
        db.session.commit()

        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, "main"
        )

        self.assertEqual(
            [playlist["name"] for playlist in playlists],
            ["Older than the flag"],
        )

    def test_the_all_pack_holds_what_is_meant_for_every_episode(self):
        self.generate_fixture_playlist("Test main pack", for_entity="asset")
        self.generate_fixture_playlist(
            "Test all playlist", for_entity="asset", is_for_all=True
        )

        playlists = playlists_service.all_playlists_for_episode(
            self.project.id, "all"
        )

        self.assertEqual(
            [playlist["name"] for playlist in playlists],
            ["Test all playlist"],
        )

    def test_generate_temp_playlist(self):
        self.generate_fixture_preview_files()
        task_id = self.task.id
        task_type_id = str(self.task.task_type_id)
        shots = playlists_service.generate_temp_playlist([task_id])
        self.assertEqual(len(shots), 1)
        self.assertEqual(str(self.shot.id), shots[0]["id"])
        self.assertEqual(len(shots[0]["preview_files"][task_type_id]), 2)

    def test_generate_temp_playlist_with_edit_task(self):
        self.generate_fixture_edit_task()
        entities = playlists_service.generate_temp_playlist(
            [self.edit_task.id]
        )
        self.assertEqual(len(entities), 1)
        self.assertEqual(str(self.edit.id), entities[0]["id"])
        self.assertEqual(entities[0]["parent_name"], "")

        self.generate_fixture_edit("Edit E01", parent_id=self.episode.id)
        edit_task = self.generate_fixture_edit_task("Edit E01 task")
        entities = playlists_service.generate_temp_playlist([edit_task.id])
        self.assertEqual(len(entities), 1)
        self.assertEqual(str(self.edit.id), entities[0]["id"])
        self.assertEqual(entities[0]["episode_name"], self.episode.name)
        self.assertEqual(entities[0]["parent_name"], self.episode.name)

    def test_generate_playlisted_entity_from_task(self):
        self.generate_fixture_preview_files()
        task_id = self.task.id
        task_type_id = str(self.task.task_type_id)
        for_entity = entities_service.get_for_entity_from_task(
            self.task.serialize()
        )
        task_type_links = projects_service.get_task_type_links(
            self.task.project_id, for_entity
        )
        shot = playlists_service.generate_playlisted_entity_from_task(
            task_id, task_type_links
        )
        self.assertEqual(str(self.shot.id), shot["id"])
        self.assertEqual(shot["parent_name"], "S01")
        self.assertEqual(len(shot["preview_files"][task_type_id]), 2)

        self.task = self.generate_fixture_task()
        task_id = self.task.id
        task_type_links = projects_service.get_task_type_links(
            self.task.project_id, for_entity
        )
        asset = playlists_service.generate_playlisted_entity_from_task(
            task_id, task_type_links
        )
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
        self.assertNotIn("shots", playlist_dict)
        self.assertEqual(playlist_dict["for_entity"], "shot")

    def test_set_preview_files_skips_empty_entity_ids(self):
        self.generate_fixture_preview_files()
        playlist_dict = {
            "shots": [
                {"id": ""},
                {"shot_id": ""},
                {"entity_id": None},
                {},
                {"id": str(self.shot.id)},
            ]
        }
        result, _ = playlists_service.set_preview_files_for_entities(
            playlist_dict
        )
        self.assertEqual(len(result["shots"]), 5)
        self.assertEqual(result["shots"][-1]["id"], str(self.shot.id))

    def test_set_preview_files_for_entities(self):
        """
        Previews grouped by entity then by task type. The task types come
        by descending priority and then by name, the previews newest
        revision first.
        """
        self.generate_fixture_preview_files()
        # Layout is created second and named after Animation, so only the
        # priority can put it first.
        self.task_type_animation.update({"priority": 1})
        self.task_type_layout.update({"priority": 2})
        layout_task = self.generate_fixture_shot_task(
            name="layout", task_type_id=self.task_type_layout.id
        )
        self.generate_fixture_preview_file(revision=1, task_id=layout_task.id)
        self.generate_fixture_preview_file(revision=2, task_id=layout_task.id)

        result, _ = playlists_service.set_preview_files_for_entities(
            {"shots": [{"id": str(self.shot.id)}]}
        )

        previews = result["shots"][0]["preview_files"]
        self.assertEqual(
            list(previews.keys()),
            [str(self.task_type_layout.id), str(self.task_type_animation.id)],
        )
        for task_type_id, entries in previews.items():
            self.assertEqual(
                [entry["revision"] for entry in entries], [2, 1], task_type_id
            )

    def test_get_playlists_for_project(self):
        """
        Every playlist of one production, whatever episode it belongs to.
        The other production keeps its own.
        """
        self.generate_fixture_playlists()
        elsewhere = Playlist.create(
            name="Elsewhere", shots={}, project_id=self.project_standard.id
        )

        playlists = playlists_service.get_playlists_for_project(
            str(self.project.id)
        )

        names = sorted(playlist["name"] for playlist in playlists)
        self.assertEqual(names, ["Playlist 1", "Playlist 3", "Playlist 4"])
        self.assertNotIn(elsewhere.name, names)

    def test_get_playlist_file_name(self):
        playlist = self.generate_fixture_playlists()
        self.assertEqual(
            playlists_service.get_playlist_file_name(playlist),
            "cosmos-landromat-playlist-4",
        )

    def test_start_and_end_build_job(self):
        """
        The two ends of a playlist build: the row the clients poll while the
        movie is being encoded, then its final status.
        """
        playlist = self.generate_fixture_playlists()

        job = playlists_service.start_build_job(playlist)
        self.assertEqual(job["status"], "running")
        self.assertEqual(job["playlist_id"], playlist["id"])
        self.assertIsNone(job["ended_at"])

        job = playlists_service.end_build_job(playlist, job, False)
        self.assertEqual(job["status"], "failed")
        self.assertIsNotNone(job["ended_at"])

    def test_end_build_job_of_a_deleted_job(self):
        # The job row may be gone by the time the build ends: the clients
        # still get the event, and the caller an empty dict rather than a
        # crash inside the queue worker.
        playlist = self.generate_fixture_playlists()
        job = playlists_service.start_build_job(playlist)
        BuildJob.get(job["id"]).delete()
        self.assertEqual(
            playlists_service.end_build_job(playlist, job, True), {}
        )
