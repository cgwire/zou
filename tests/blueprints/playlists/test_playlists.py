import os

from flask import g

from tests.base import ApiDBTestCase
from zou.app import app

from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.models.playlist_share_link import PlaylistShareLink
from zou.app.services import (
    playlist_sharing_service,
    playlists_service,
    projects_service,
)


class PlaylistTestCase(ApiDBTestCase):
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

    def test_get_playlists(self):
        self.generate_fixture_playlist("Playlist 1")
        playlists = self.get(f"data/projects/{self.project_id}/playlists")
        self.assertEqual(len(playlists), 1)

    def test_get_all_episodes_playlists_filtered_by_entity(self):
        self.generate_fixture_playlist(
            "All assets", for_entity="asset", is_for_all=True
        )
        self.generate_fixture_playlist(
            "All shots", for_entity="shot", is_for_all=True
        )
        self.generate_fixture_playlist(
            "Episode shots", episode_id=self.episode_id
        )
        base = f"data/projects/{self.project_id}/episodes/all/playlists"
        self.assertEqual(
            {p["name"] for p in self.get(base)}, {"All assets", "All shots"}
        )
        self.assertEqual(
            [p["name"] for p in self.get(f"{base}?for_entity=shot")],
            ["All shots"],
        )
        self.assertEqual(
            [p["name"] for p in self.get(f"{base}?for_entity=asset")],
            ["All assets"],
        )

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
            f"data/projects/{self.project_id}/playlists?task_type_id={self.task_type_animation.id}"
        )
        self.assertEqual(len(playlists), 2)
        self.assertEqual(playlists[0]["name"], "Playlist 3")
        self.assertEqual(playlists[1]["name"], "Playlist 2")

    def test_delete_playlist(self):
        self.generate_fixture_playlist("Playlist 1")
        playlists = self.get(f"data/projects/{self.project_id}/playlists")
        self.delete(f"data/playlists/{playlists[0]['id']}")
        playlists = self.get(f"data/projects/{self.project_id}/playlists")
        self.assertEqual(playlists, [])

    def assert_dependents_go_with_the_playlist(self, remove):
        """
        Whatever hangs off a playlist goes when the playlist goes. Each
        dependent gets its own playlist so one broken cascade does not leave
        a row the next case trips over.
        """

        def create_notification(playlist_id):
            Notification.create(
                type="playlist-ready",
                person_id=self.user["id"],
                author_id=self.user["id"],
                playlist_id=playlist_id,
            )

        def create_share_link(playlist_id):
            playlist_sharing_service.create_share_link(
                playlist_id, self.user["id"]
            )

        dependents = {
            "notifications": (create_notification, Notification),
            "share links": (create_share_link, PlaylistShareLink),
        }
        for dependent, (create, model) in dependents.items():
            with self.subTest(dependent=dependent):
                self.generate_fixture_playlist(dependent)
                playlist_id = str(self.playlist.id)
                create(playlist_id)

                remove(playlist_id)

                self.get(f"data/playlists/{playlist_id}", 404)
                self.assertEqual(
                    model.query.filter_by(playlist_id=playlist_id).all(), []
                )

    def test_the_delete_route_takes_the_dependents_with_it(self):
        self.assert_dependents_go_with_the_playlist(
            lambda playlist_id: self.delete(f"data/playlists/{playlist_id}")
        )

    def test_remove_playlist_takes_the_dependents_with_it(self):
        """
        The service and the CRUD route share remove_playlist_dependents;
        both are exercised so the cascade cannot drift apart again.
        """
        self.assert_dependents_go_with_the_playlist(
            playlists_service.remove_playlist
        )

    def test_create_playlist_for_each_entity_type(self):
        """
        `for_entity` round-trips for every supported entity type.

        The column is permissive `String(10)` but the CRUD whitelists the
        set so a stray value cannot land in storage; this test pins the
        contract for each accepted value.

        """
        for for_entity in ("shot", "asset", "sequence", "edit", "episode"):
            created = self.post(
                "data/playlists/",
                {
                    "name": f"Playlist {for_entity}",
                    "project_id": self.project_id,
                    "for_entity": for_entity,
                },
                201,
            )
            self.assertEqual(created["for_entity"], for_entity)
            fetched = self.get(f"data/playlists/{created['id']}")
            self.assertEqual(fetched["for_entity"], for_entity)

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

    def test_concurrent_zip_builds_keep_their_own_file(self):
        # Two downloads of the same playlist: the second build must not
        # remove the archive the first one is about to send.
        playlist = self.generate_fixture_playlist("Playlist 1")
        first_path = playlists_service.build_playlist_zip_file(playlist)
        second_path = playlists_service.build_playlist_zip_file(playlist)
        try:
            self.assertNotEqual(first_path, second_path)
            self.assertTrue(os.path.exists(first_path))
        finally:
            for path in (first_path, second_path):
                if os.path.exists(path):
                    os.remove(path)

    def test_download_playlist(self):
        self.generate_fixture_playlist("Playlist 1", for_client=False)
        result_file_path = self.get_file_path("playlist.zip")
        url_path = f"/data/playlists/{self.playlist.id}/download/zip"
        self.create_test_folder()
        self.download_file(url_path, result_file_path)

        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()
        self.download_file(url_path, result_file_path, 403)
        self.generate_fixture_playlist("Playlist 2", for_client=True)
        url_path = f"/data/playlists/{self.playlist.id}/download/zip"
        self.download_file(url_path, result_file_path)
