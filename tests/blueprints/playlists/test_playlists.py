from tests.base import ApiDBTestCase

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
        PlaylistResource.pre_delete and playlists_service.remove_playlist are
        two implementations of one cascade, not one shared by both, so the
        service needs its own case: a dependent added to one route is not
        added to the other.
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

    def test_update_playlist_rejects_unknown_for_entity(self):
        self.generate_fixture_playlist("Playlist 1")
        self.put(
            f"data/playlists/{self.playlist.id}",
            {"for_entity": "banana"},
            400,
        )

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
