from flask import g

from tests.base import ApiDBTestCase

from zou.app.models.build_job import BuildJob
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.services import projects_service, tasks_service
from zou.app.utils import fields


class PlaylistRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_episode("E01")
        self.generate_fixture_sequence("SE01")
        self.generate_fixture_shot("SH01")
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)

    def test_get_all_project_playlists(self):
        self.generate_fixture_playlist("Playlist 1")
        result = self.get(f"/data/projects/{self.project_id}/playlists/all")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_get_episode_playlists(self):
        """
        The playlists of one episode. A playlist of the next episode, and one
        attached to no episode at all, are not this episode's business.
        """
        here = self.episode
        self.generate_fixture_playlist("Episode Playlist", episode_id=here.id)
        elsewhere = self.generate_fixture_episode("E02")
        self.generate_fixture_playlist("Next", episode_id=elsewhere.id)
        self.generate_fixture_playlist("Loose")

        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode_id}/playlists"
        )

        self.assertEqual(
            [playlist["name"] for playlist in result], ["Episode Playlist"]
        )

    def test_get_episode_playlists_is_scoped_to_the_production(self):
        """
        The episode listing must stay inside the production it is asked
        about: an episode id of another production returns nothing, whoever
        asks.
        """
        elsewhere = self.generate_fixture_project_standard()
        other_episode = self.generate_fixture_episode(
            "E99", project_id=elsewhere.id
        )
        self.generate_fixture_playlist(
            "Theirs",
            project_id=elsewhere.id,
            episode_id=other_episode.id,
        )

        playlists = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{other_episode.id}/playlists"
        )

        self.assertEqual(playlists, [])

    def test_get_project_playlist(self):
        self.generate_fixture_playlist("Single Playlist")
        playlists = self.get(f"/data/projects/{self.project_id}/playlists")
        playlist_id = playlists[0]["id"]
        result = self.get(
            f"/data/projects/{self.project_id}" f"/playlists/{playlist_id}"
        )
        self.assertEqual(result["id"], playlist_id)

    def test_get_entity_preview_files(self):
        """
        The previews of an entity, keyed by the task type they were made
        for.
        """
        path = f"/data/playlists/entities/{self.shot.id}/preview-files"
        self.assertEqual(self.get(path), {})
        preview_file = self.generate_fixture_preview_file(
            task_id=self.shot_task.id
        )

        result = self.get(path)

        task_type_id = str(self.shot_task.task_type_id)
        self.assertEqual(
            [preview["id"] for preview in result[task_type_id]],
            [str(preview_file.id)],
        )

    def test_get_entity_preview_files_vendor_assigned(self):
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        path = f"/data/playlists/entities/{self.shot.id}/preview-files"
        self.get(path, 403)
        projects_service.add_team_member(
            self.project.id, self.user_vendor["id"]
        )
        tasks_service.assign_task(self.shot_task.id, self.user_vendor["id"])
        result = self.get(path)
        self.assertIsInstance(result, dict)

    def test_get_entity_preview_files_vendor_not_assigned(self):
        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project.id, self.user_vendor["id"]
        )
        self.log_in_vendor()
        path = f"/data/playlists/entities/{self.shot.id}/preview-files"
        self.get(path, 403)

    def test_get_project_build_jobs(self):
        self.assertEqual(
            self.get(f"/data/projects/{self.project_id}/build-jobs"), []
        )
        self.generate_fixture_playlist("Playlist 1")
        job = BuildJob.create(
            status="running",
            job_type="movie",
            playlist_id=self.playlist.id,
        )

        result = self.get(f"/data/projects/{self.project_id}/build-jobs")

        self.assertEqual([entry["id"] for entry in result], [str(job.id)])

    def test_create_temp_playlist(self):
        """
        A playlist built on the fly from a list of tasks: one entry per task,
        carrying the entity that task is on.
        """
        result = self.post(
            f"/data/projects/{self.project_id}/playlists/temp",
            {"task_ids": [str(self.shot_task.id)]},
            200,
        )

        self.assertEqual(
            [entity["id"] for entity in result], [str(self.shot.id)]
        )

    def test_create_temp_playlist_from_entities(self):
        """
        The same playlist built from entities: one entry per entity, on the
        task holding the preview it was last reviewed on.
        """
        preview_file = self.generate_fixture_preview_file(
            task_id=self.shot_task.id
        )
        self.shot_task.update({"last_preview_file_id": preview_file.id})

        result = self.post(
            f"/data/projects/{self.project_id}/playlists/temp",
            {"entity_ids": [str(self.shot.id)]},
            200,
        )

        self.assertEqual(
            [entity["id"] for entity in result], [str(self.shot.id)]
        )

    def test_create_temp_playlist_vendor_assigned(self):
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        path = f"/data/projects/{self.project_id}/playlists/temp"
        data = {"task_ids": [str(self.shot_task.id)]}
        self.post(path, data, 403)
        projects_service.add_team_member(
            self.project.id, self.user_vendor["id"]
        )
        tasks_service.assign_task(self.shot_task.id, self.user_vendor["id"])
        result = self.post(path, data, 200)
        self.assertIsInstance(result, list)

    def test_create_temp_playlist_vendor_not_assigned(self):
        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project.id, self.user_vendor["id"]
        )
        self.log_in_vendor()
        path = f"/data/projects/{self.project_id}/playlists/temp"
        data = {"task_ids": [str(self.shot_task.id)]}
        self.post(path, data, 403)

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

    def test_add_entities_to_playlist(self):
        first_shot_id = str(self.shot.id)
        self.generate_fixture_shot("SH02")
        second_shot_id = str(self.shot.id)
        self.generate_fixture_playlist("Add Entities Playlist")
        playlist_id = str(self.playlist.id)
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entities",
            {
                "entities": [
                    {"entity_id": first_shot_id},
                    {"entity_id": second_shot_id},
                ]
            },
            200,
        )
        entity_ids = [shot["entity_id"] for shot in result["shots"]]
        self.assertEqual(entity_ids, [first_shot_id, second_shot_id])

    def test_add_entities_to_playlist_skips_duplicate_couple(self):
        # The same (entity, preview) couple twice collapses to one entry.
        self.generate_fixture_preview_file(
            revision=1, task_id=self.shot_task.id
        )
        preview_id = str(self.preview_file.id)
        self.generate_fixture_playlist("Add Entities Playlist")
        playlist_id = str(self.playlist.id)
        shot_id = str(self.shot.id)
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entities",
            {
                "entities": [
                    {"entity_id": shot_id, "preview_file_id": preview_id},
                    {"entity_id": shot_id, "preview_file_id": preview_id},
                ]
            },
            200,
        )
        couples = [
            (shot["entity_id"], shot.get("preview_file_id"))
            for shot in result["shots"]
        ]
        self.assertEqual(couples, [(shot_id, preview_id)])

    def test_add_entities_same_entity_twice_with_different_previews(self):
        # The same entity may appear several times with different previews.
        self.generate_fixture_preview_file(
            revision=1, task_id=self.shot_task.id
        )
        first_preview_id = str(self.preview_file.id)
        self.generate_fixture_preview_file(
            revision=2, task_id=self.shot_task.id
        )
        second_preview_id = str(self.preview_file.id)
        self.generate_fixture_playlist("Add Entities Playlist")
        playlist_id = str(self.playlist.id)
        shot_id = str(self.shot.id)
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entities",
            {
                "entities": [
                    {
                        "entity_id": shot_id,
                        "preview_file_id": first_preview_id,
                    },
                    {
                        "entity_id": shot_id,
                        "preview_file_id": second_preview_id,
                    },
                ]
            },
            200,
        )
        couples = [
            (shot["entity_id"], shot.get("preview_file_id"))
            for shot in result["shots"]
        ]
        self.assertEqual(
            couples,
            [(shot_id, first_preview_id), (shot_id, second_preview_id)],
        )

    def test_add_entities_to_playlist_picks_latest_preview_file(self):
        # No preview given: the entity's latest preview is resolved by
        # revision. Create the highest revision first so an ordering by
        # created_at would pick the wrong one.
        self.generate_fixture_preview_file(
            revision=2, task_id=self.shot_task.id
        )
        latest_preview_file_id = str(self.preview_file.id)
        self.generate_fixture_preview_file(
            revision=1, task_id=self.shot_task.id
        )
        self.generate_fixture_playlist("Add Entities Playlist")
        playlist_id = str(self.playlist.id)
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entities",
            {"entities": [{"entity_id": str(self.shot.id)}]},
            200,
        )
        self.assertEqual(
            result["shots"][0]["preview_file_id"], latest_preview_file_id
        )

    def test_add_entities_to_playlist_uses_playlist_task_type(self):
        # The shot has a preview on its animation task (from setUp)...
        self.generate_fixture_preview_file(
            revision=1, task_id=self.shot_task.id
        )
        animation_preview_id = str(self.preview_file.id)
        # ...and a higher-revision preview on a layout task.
        layout_task = self.generate_fixture_shot_task(
            name="Layout", task_type_id=self.task_type_layout.id
        )
        self.generate_fixture_preview_file(revision=9, task_id=layout_task.id)
        # The playlist is scoped to the animation task type.
        self.generate_fixture_playlist(
            "Task Type Playlist", task_type_id=self.task_type_animation.id
        )
        playlist_id = str(self.playlist.id)
        result = self.post(
            f"/actions/playlists/{playlist_id}/add-entities",
            {"entities": [{"entity_id": str(self.shot.id)}]},
            200,
        )
        # Despite the layout preview's higher revision, the playlist task type
        # wins, so the animation preview is picked.
        self.assertEqual(
            result["shots"][0]["preview_file_id"], animation_preview_id
        )

    def test_add_entities_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        playlist = self._create_playlist("Artist Playlist")
        self.log_in_cg_artist()
        self.post(
            f"/actions/playlists/{playlist['id']}/add-entities",
            {"entities": [{"entity_id": str(self.shot.id)}]},
            403,
        )

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

    def _add_supervisor_to_team(self):
        """
        A supervisor can only create a playlist on a project they belong to
        (check_supervisor_project_access), so the ones editing theirs are on
        the team. Building the playlist through the model skips that.
        """
        self.project.team.append(Person.get(self.user_supervisor["id"]))
        self.project.save()

    def test_add_entity_as_supervisor_creator(self):
        self.generate_fixture_user_supervisor()
        self._add_supervisor_to_team()
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
        self._add_supervisor_to_team()
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

    def test_update_playlist_as_supervisor_outside_the_team_is_forbidden(self):
        # created_by is null on every playlist predating the column, and a
        # failed has_manager_project_access clears the project role slot, so
        # the supervisor branch used to read the global role and let a
        # supervisor of another production through.
        self.generate_fixture_user_supervisor()
        playlist = self._create_playlist("Orphan Playlist")
        self.assertIsNone(playlist["created_by"])
        self.log_in_supervisor()
        self.put(
            f"/data/playlists/{playlist['id']}",
            {"name": "Renamed from outside"},
            403,
        )
        self.delete(f"/data/playlists/{playlist['id']}", 403)

    def test_update_orphan_playlist_as_supervisor_of_the_team(self):
        self.generate_fixture_user_supervisor()
        self._add_supervisor_to_team()
        playlist = self._create_playlist("Orphan Playlist")
        self.log_in_supervisor()
        self.put(
            f"/data/playlists/{playlist['id']}",
            {"name": "Renamed by the team supervisor"},
            200,
        )

    def test_delete_playlist_as_supervisor_creator(self):
        self.generate_fixture_user_supervisor()
        self._add_supervisor_to_team()
        playlist = self._create_playlist(
            "Supervisor Playlist", creator_id=self.user_supervisor["id"]
        )
        self.log_in_supervisor()
        self.delete(f"/data/playlists/{playlist['id']}")

    def test_get_build_job(self):
        self.generate_fixture_playlist("Playlist")
        playlist_id = str(self.playlist.id)
        build_job = self.generate_fixture_build_job("2026-08-05T12:00:00")

        result = self.get(
            f"/data/playlists/{playlist_id}/jobs/{build_job['id']}"
        )
        self.assertEqual(result["id"], build_job["id"])

    def test_build_job_must_belong_to_the_playlist(self):
        """
        The job id comes from the client next to a playlist id it has access
        to. Loading it without checking the link would serve, and let delete,
        the build job of any other playlist.
        """
        self.generate_fixture_playlist("Playlist")
        build_job = self.generate_fixture_build_job("2026-08-05T12:00:00")
        other_playlist = self.generate_fixture_playlist("Other Playlist")

        path = f"/data/playlists/{other_playlist['id']}/jobs/{build_job['id']}"
        self.get_404(path)
        self.get_404(f"{path}/build/mp4")
        self.delete_404(path)

    def test_download_unfinished_build(self):
        """
        The download route reads the movie from the store, so it must turn a
        build that never succeeded away before looking for a file that is not
        there.
        """
        self.generate_fixture_playlist("Playlist")
        playlist_id = str(self.playlist.id)
        build_job = self.generate_fixture_build_job("2026-08-05T12:00:00")
        BuildJob.get(build_job["id"]).update({"status": "running"})

        self.get(
            f"/data/playlists/{playlist_id}/jobs/{build_job['id']}/build/mp4",
            400,
        )

    def test_delete_build_job(self):
        self.generate_fixture_playlist("Playlist")
        playlist_id = str(self.playlist.id)
        build_job = self.generate_fixture_build_job("2026-08-05T12:00:00")

        path = f"/data/playlists/{playlist_id}/jobs/{build_job['id']}"
        self.delete(path)
        self.get_404(path)

    def test_notify_clients(self):
        self.generate_fixture_playlist("Playlist")
        playlist_id = str(self.playlist.id)
        self.generate_fixture_user_client()
        client_id = self.user_client["id"]
        projects_service.add_team_member(self.project_id, client_id)

        self.post(f"/data/playlists/{playlist_id}/notify-clients", {}, 200)

        notifications = Notification.query.filter_by(
            person_id=client_id, type="playlist-ready"
        ).all()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(str(notifications[0].playlist_id), playlist_id)


class ProjectPlaylistReadTestCase(ApiDBTestCase):
    """
    Reading one playlist through the route of a production, which holds
    an internal playlist and one shared with clients.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)
        self.internal = self.generate_fixture_playlist("Internal")
        self.for_client = self.generate_fixture_playlist(
            "For client", for_client=True
        )

    def playlist_path(self, playlist, project_id=None):
        project_id = project_id or self.project_id
        return f"/data/projects/{project_id}/playlists/{playlist['id']}"

    def read_as(self, user, role=None):
        """
        Join the production, with a role of one's own on it if given, and
        log in. flask.g outlives the requests of a test: the role resolved
        for the previous caller goes, as between two real requests.
        """
        projects_service.add_team_member(
            self.project_id, user["id"], role=role
        )
        self.log_in(user["email"])
        g.pop("project_role", None)
        return user

    def get_afresh(self, path, code=200):
        """
        Get given path as a request of its own: flask.g outlives the
        requests of a test, so a gate run before the production is resolved
        would read the role the previous request left there.
        """
        g.pop("project_role", None)
        return self.get(path, code)

    def test_a_playlist_of_another_production_is_not_found_here(self):
        """
        The playlist id comes from the client next to a production it may
        access: the rights were checked on that production, and a playlist
        of any other one was served through it, to an admin as to a member
        of both.
        """
        other_project_id = str(self.generate_fixture_project_standard().id)
        elsewhere = self.generate_fixture_playlist(
            "Elsewhere", project_id=other_project_id
        )
        here = self.playlist_path(elsewhere)
        there = self.playlist_path(elsewhere, other_project_id)

        self.get_404(here)
        self.assertEqual(self.get(there)["id"], elsewhere["id"])
        # Nor is an id of no playlist, or one that is no id at all.
        self.get_404(self.playlist_path({"id": fields.gen_uuid()}))
        self.get_404(self.playlist_path({"id": "not-an-id"}))

        manager = self.read_as(self.generate_fixture_user_manager())
        projects_service.add_team_member(other_project_id, manager["id"])
        self.get_404(here)
        self.assertEqual(self.get(there)["id"], elsewhere["id"])

    def test_a_client_opens_the_shared_playlists_only(self):
        self.read_as(self.generate_fixture_user_client())

        self.get(self.playlist_path(self.internal), 403)
        self.assertEqual(
            self.get(self.playlist_path(self.for_client))["id"],
            self.for_client["id"],
        )

    def test_a_client_by_project_role_opens_the_shared_ones_only(self):
        """
        The rule reads the role held on the production, which the access
        check resolves first: a global artist made client there is one.
        """
        self.read_as(self.generate_fixture_user_cg_artist(), role="client")

        self.get(self.playlist_path(self.internal), 403)
        self.get(self.playlist_path(self.for_client))

    def test_the_team_opens_every_playlist(self):
        """
        Reading a playlist is broader than downloading it: an artist
        watches the playlists of their production, and so does a client
        made artist there.
        """
        team = {
            "manager": (self.generate_fixture_user_manager, None),
            "supervisor": (self.generate_fixture_user_supervisor, None),
            "artist": (self.generate_fixture_user_cg_artist, None),
            "client made artist": (self.generate_fixture_user_client, "user"),
        }
        for reason, (fixture, role) in team.items():
            with self.subTest(reason=reason):
                self.read_as(fixture(), role=role)

                for playlist in (self.internal, self.for_client):
                    self.assertEqual(
                        self.get(self.playlist_path(playlist))["id"],
                        playlist["id"],
                    )

    def test_a_vendor_by_project_role_reads_no_playlist_here(self):
        """
        The vendor gate of the playlist routes of a production ran before
        the production was resolved, so on the global role: a client or an
        artist made vendor there listed and opened its playlists, internal
        ones included, which the CRUD read refuses them.
        """
        vendors = {
            "client made vendor": self.generate_fixture_user_client,
            "artist made vendor": self.generate_fixture_user_cg_artist,
        }
        for reason, fixture in vendors.items():
            with self.subTest(reason=reason):
                self.read_as(fixture(), role="vendor")

                self.get_afresh(
                    f"/data/projects/{self.project_id}/playlists", 403
                )
                self.get_afresh(
                    f"/data/projects/{self.project_id}/episodes/main"
                    "/playlists",
                    403,
                )
                for playlist in (self.internal, self.for_client):
                    self.get_afresh(self.playlist_path(playlist), 403)

    def test_a_vendor_made_artist_reads_the_playlists_here(self):
        """
        The other way round: a vendor made artist on a production is no
        vendor there, as the CRUD read of a playlist already found.
        """
        self.read_as(self.generate_fixture_user_vendor(), role="user")

        names = {
            playlist["name"]
            for playlist in self.get_afresh(
                f"/data/projects/{self.project_id}/playlists"
            )
        }
        self.assertEqual(names, {"Internal", "For client"})
        self.assertEqual(
            self.get_afresh(self.playlist_path(self.internal))["id"],
            self.internal["id"],
        )
