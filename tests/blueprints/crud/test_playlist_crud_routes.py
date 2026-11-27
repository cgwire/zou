from flask import g

from tests.base import ApiDBTestCase
from zou.app import app
from zou.app.models.person import Person
from zou.app.models.playlist import Playlist
from zou.app.services import projects_service


class PlaylistCrudTestCase(ApiDBTestCase):
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

    def test_crud_list_hides_internal_playlists_from_clients(self):
        self.generate_fixture_playlist("Internal")
        self.generate_fixture_playlist("For client", for_client=True)
        self.generate_fixture_user_client()
        self.project.team.append(Person.get(self.user_client["id"]))
        self.project.save()
        self.log_in_client()

        names = {playlist["name"] for playlist in self.get("data/playlists")}
        self.assertEqual(names, {"For client"})

        dedicated = self.get(f"data/projects/{self.project_id}/playlists")
        self.assertEqual({p["name"] for p in dedicated}, {"For client"})

    def test_crud_list_scopes_to_user_projects(self):
        self.generate_fixture_playlist("In project")
        self.generate_fixture_project_standard()
        self.generate_fixture_playlist(
            "Elsewhere", project_id=self.project_standard.id
        )
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_vendor()

        names = {playlist["name"] for playlist in self.get("data/playlists")}
        self.assertEqual(names, {"In project", "Elsewhere"})

        self.log_in_cg_artist()
        self.assertEqual(self.get("data/playlists"), [])

        self.project.team.append(Person.get(self.user_cg_artist["id"]))
        self.project.save()
        self.log_in_cg_artist()
        names = {playlist["name"] for playlist in self.get("data/playlists")}
        self.assertEqual(names, {"In project"})

        self.project.team.append(Person.get(self.user_vendor["id"]))
        self.project.save()
        self.log_in_vendor()
        self.get("data/playlists", 403)

    def join_two_productions(self, user, role=None):
        """
        This production holds an internal playlist and one shared with
        clients, another one an internal playlist. Given user joins both,
        with given role on this one only, and logs in. Return the internal
        playlist of this production.
        """
        internal = self.generate_fixture_playlist("Internal")
        self.generate_fixture_playlist("For client", for_client=True)
        other_project_id = str(self.generate_fixture_project_standard().id)
        self.generate_fixture_playlist(
            "Elsewhere", project_id=other_project_id
        )
        projects_service.add_team_member(
            self.project_id, user["id"], role=role
        )
        projects_service.add_team_member(other_project_id, user["id"])
        self.log_in(user["email"])
        return internal

    def list_playlist_names(self):
        return {playlist["name"] for playlist in self.get("data/playlists")}

    def test_crud_list_narrows_a_client_on_each_of_their_productions(self):
        """
        A client is narrowed on every production they belong to, through
        the query string filters as well.
        """
        internal = self.join_two_productions(
            self.generate_fixture_user_client()
        )

        self.assertEqual(self.list_playlist_names(), {"For client"})
        self.assertEqual(self.get(f"data/playlists?id={internal['id']}"), [])

    def test_crud_list_narrows_a_client_by_project_role_there_only(self):
        """
        A listing resolves no project, so the client rule read the global
        role: an artist made client on a production listed its internal
        playlists, through the query string filters as well.
        """
        internal = self.join_two_productions(
            self.generate_fixture_user_cg_artist(), role="client"
        )

        self.assertEqual(
            self.list_playlist_names(), {"For client", "Elsewhere"}
        )
        self.assertEqual(self.get(f"data/playlists?id={internal['id']}"), [])

    def test_crud_list_lets_a_client_made_artist_see_internal_playlists(self):
        """
        The other way round: a client made artist on a production was
        narrowed there as well, as on the productions where they stay a
        client.
        """
        self.join_two_productions(
            self.generate_fixture_user_client(), role="user"
        )

        self.assertEqual(
            self.list_playlist_names(), {"Internal", "For client"}
        )

    def test_crud_list_shows_a_client_made_vendor_no_playlist_there(self):
        """
        A client made vendor on a production is no client there: reading
        that role must not list its internal playlists, as the client rule
        on the global role did not. A vendor reads no playlist of the
        production, as a playlist read refuses them there.
        """
        internal = self.join_two_productions(
            self.generate_fixture_user_client(), role="vendor"
        )

        self.assertEqual(self.list_playlist_names(), set())
        self.assertEqual(self.get(f"data/playlists?id={internal['id']}"), [])

    def test_crud_list_shows_an_artist_made_vendor_no_playlist_there(self):
        """
        An artist made vendor on a production listed all its playlists,
        which a playlist read refuses them there.
        """
        self.join_two_productions(
            self.generate_fixture_user_cg_artist(), role="vendor"
        )

        self.assertEqual(self.list_playlist_names(), {"Elsewhere"})

    def test_crud_get_hides_internal_playlists_from_clients(self):
        internal = self.generate_fixture_playlist("Internal")
        for_client = self.generate_fixture_playlist(
            "For client", for_client=True
        )
        client = self.generate_fixture_user_client()
        projects_service.add_team_member(self.project_id, client["id"])
        self.log_in_client()

        self.get(f"data/playlists/{internal['id']}", 403)
        self.assertEqual(
            self.get(f"data/playlists/{for_client['id']}")["id"],
            for_client["id"],
        )

    def test_crud_get_follows_the_project_role_of_a_client(self):
        internal = self.generate_fixture_playlist("Internal")
        for_client = self.generate_fixture_playlist(
            "For client", for_client=True
        )
        artist = self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, artist["id"], role="client"
        )
        self.log_in_cg_artist()

        self.get(f"data/playlists/{internal['id']}", 403)
        self.get(f"data/playlists/{for_client['id']}")

    def test_crud_get_lets_the_team_read_internal_playlists(self):
        internal = self.generate_fixture_playlist("Internal")
        team = {
            "manager": self.generate_fixture_user_manager,
            "supervisor": self.generate_fixture_user_supervisor,
            "artist": self.generate_fixture_user_cg_artist,
        }
        for role, fixture in team.items():
            with self.subTest(role=role):
                user = fixture()
                projects_service.add_team_member(self.project_id, user["id"])
                self.log_in(user["email"])
                # flask.g outlives the requests of a test: the role resolved
                # for the previous member goes, as between real requests.
                g.pop("project_role", None)

                self.assertEqual(
                    self.get(f"data/playlists/{internal['id']}")["id"],
                    internal["id"],
                )

    def test_create_playlist_keeps_its_for_entity(self):
        """
        `for_entity` round-trips. The column is a permissive `String(10)`:
        test_create_playlist_rejects_unknown_for_entity pins the whitelist.
        """
        created = self.post(
            "data/playlists/",
            {
                "name": "Playlist edit",
                "project_id": self.project_id,
                "for_entity": "edit",
            },
            201,
        )
        self.assertEqual(created["for_entity"], "edit")
        fetched = self.get(f"data/playlists/{created['id']}")
        self.assertEqual(fetched["for_entity"], "edit")

    def test_create_playlist_rejects_unknown_for_entity(self):
        self.post(
            "data/playlists/",
            {
                "name": "Bad playlist",
                "project_id": self.project_id,
                "for_entity": "banana",
            },
            400,
        )

    def test_create_playlist_duplicate_name_is_a_client_error(self):
        self.generate_fixture_playlist(
            "Playlist 1", episode_id=self.episode_id
        )
        data = {
            "name": "Playlist 1",
            "project_id": self.project_id,
            "episode_id": self.episode_id,
        }
        with self.assertNoLogs(app.logger, level="ERROR"):
            result = self.post("data/playlists/", data, 400)
        self.assertEqual(
            result["message"],
            "A record with the same unique values already exists.",
        )

    def test_update_playlist_rejects_unknown_for_entity(self):
        self.generate_fixture_playlist("Playlist 1")
        self.put(
            f"data/playlists/{self.playlist.id}",
            {"for_entity": "banana"},
            400,
        )


class PlaylistCrudWriteTestCase(ApiDBTestCase):
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

    def generate_fixture_foreign_preview_file(self):
        """
        Give SH01 a preview, then return SH02 with a preview of its own.
        """
        self.generate_fixture_preview_file(
            revision=1, task_id=self.shot_task.id
        )
        self.own_preview_file_id = str(self.preview_file.id)
        self.first_shot_id = str(self.shot.id)
        other_shot = self.generate_fixture_shot("SH02")
        other_task = self.generate_fixture_shot_task(shot_id=other_shot.id)
        self.generate_fixture_preview_file(revision=1, task_id=other_task.id)
        self.foreign_preview_file_id = str(self.preview_file.id)
        return str(other_shot.id)

    def test_create_playlist_unpins_a_foreign_preview(self):
        self.generate_fixture_foreign_preview_file()
        created = self.post(
            "data/playlists/",
            {
                "name": "Playlist created with a foreign pin",
                "project_id": self.project_id,
                "for_entity": "shot",
                "shots": [
                    {
                        "entity_id": self.first_shot_id,
                        "preview_file_id": self.foreign_preview_file_id,
                    },
                    {
                        "entity_id": self.first_shot_id,
                        "preview_file_id": self.own_preview_file_id,
                    },
                ],
            },
            201,
        )
        self.assertEqual(
            [shot["preview_file_id"] for shot in created["shots"]],
            [None, self.own_preview_file_id],
        )

    def test_update_playlist_keeps_an_own_pin_written_in_uppercase(self):
        # The playlist reads match the lowercase form of the preview ids.
        self.generate_fixture_foreign_preview_file()
        self.generate_fixture_playlist("Playlist with an uppercase pin")
        result = self.put(
            f"data/playlists/{self.playlist.id}",
            {
                "shots": [
                    {
                        "entity_id": self.first_shot_id,
                        "preview_file_id": self.own_preview_file_id.upper(),
                    }
                ]
            },
        )
        self.assertEqual(
            result["shots"][0]["preview_file_id"], self.own_preview_file_id
        )

    def test_update_playlist_unpins_a_foreign_preview(self):
        other_shot_id = self.generate_fixture_foreign_preview_file()
        self.generate_fixture_playlist("Playlist with a foreign pin")
        result = self.put(
            f"data/playlists/{self.playlist.id}",
            {
                "shots": [
                    {
                        "entity_id": self.first_shot_id,
                        "preview_file_id": self.foreign_preview_file_id,
                    },
                    {
                        "entity_id": other_shot_id,
                        "preview_file_id": self.foreign_preview_file_id,
                    },
                    {
                        "entity_id": self.first_shot_id,
                        "preview_file_id": "not-an-id",
                    },
                ]
            },
        )
        self.assertEqual(
            [shot["preview_file_id"] for shot in result["shots"]],
            [None, self.foreign_preview_file_id, None],
        )

    def test_update_playlist_keeps_an_entry_without_preview(self):
        # Such an entry is served without the preview_file_id key: a client
        # saving back the shots it read must not lose it.
        self.generate_fixture_playlist(
            "Playlist with an entry without preview"
        )
        result = self.put(
            f"data/playlists/{self.playlist.id}",
            {
                "shots": [
                    {"entity_id": str(self.shot.id)},
                    {"entity_id": None, "id": str(self.shot.id)},
                    {"preview_file_id": None},
                ]
            },
        )
        self.assertEqual(
            result["shots"],
            [{"entity_id": str(self.shot.id), "preview_file_id": None}] * 2,
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
        self._add_supervisor_to_team()
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
