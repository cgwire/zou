from tests.base import ApiDBTestCase

from zou.app.services import (
    breakdown_service,
)


class BreakdownServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(BreakdownServiceTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)
        self.shot_id = str(self.shot.id)
        self.sequence_id = str(self.sequence.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)
        self.generate_fixture_shot("SH02")
        self.asset = self.generate_fixture_asset_character("Dog")

    def test_get_episode_casting(self):
        casting = breakdown_service.get_casting(self.shot.id)
        self.assertListEqual(casting, [])
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put(
            f"/data/projects/{self.project_id}/entities/{self.episode_id}/casting",
            new_casting,
        )
        casting = self.get(
            f"/data/projects/{self.project_id}/entities/{self.episode_id}/casting"
        )
        self.assertEqual(len(casting), 2)
        self.assertEqual(casting[0]["asset_name"], "Rabbit")
        self.assertEqual(casting[1]["asset_name"], "Tree")

    def test_get_shot_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put(
            f"/data/projects/{self.project_id}/entities/{self.shot_id}/casting",
            new_casting,
        )
        casting = self.get(
            f"/data/projects/{self.project_id}/entities/{self.shot_id}/casting"
        )
        self.assertEqual(len(casting), 2)
        self.assertEqual(casting[0]["asset_name"], "Rabbit")
        self.assertEqual(casting[1]["asset_name"], "Tree")

        # Test automatic addition to related episode
        casting = self.get(
            f"/data/projects/{self.project_id}/entities/{self.episode_id}/casting"
        )
        self.assertEqual(len(casting), 2)
        self.assertEqual(casting[0]["asset_name"], "Rabbit")
        self.assertEqual(casting[1]["asset_name"], "Tree")

    def test_remove_from_episode_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put(
            f"/data/projects/{self.project_id}/entities/{self.shot_id}/casting",
            new_casting,
        )

        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
        ]
        self.put(
            f"/data/projects/{self.project_id}/entities/{self.episode_id}/casting",
            new_casting,
        )

        casting = self.get(
            f"/data/projects/{self.project_id}/entities/{self.episode_id}/casting"
        )
        self.assertEqual(len(casting), 1)
        casting = self.get(
            f"/data/projects/{self.project_id}/entities/{self.shot_id}/casting"
        )
        self.assertEqual(len(casting), 1)
        self.assertEqual(casting[0]["asset_name"], "Tree")

    def test_get_episode_assets(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put(
            f"/data/projects/{self.project_id}/entities/{self.shot_id}/casting",
            new_casting,
        )
        assets = self.get(f"/data/assets?episode_id={self.episode_id}")
        assets = sorted(assets, key=lambda a: a["name"])
        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0]["name"], "Rabbit")
        self.assertEqual(assets[1]["name"], "Tree")

        self.asset.update({"source_id": self.episode_id})
        assets = self.get(f"/data/assets?episode_id={self.episode_id}")
        self.assertEqual(len(assets), 3)

    def test_get_project_entity_links(self):
        for i in range(10):
            shot = self.generate_fixture_shot(f"SH00{i}")
            new_casting = [
                {"asset_id": self.asset_id, "nb_occurences": 1},
                {"asset_id": self.asset_character_id, "nb_occurences": 1},
            ]
            self.put(
                f"/data/projects/{self.project_id}/entities/{shot.id}/casting",
                new_casting,
            )
        alllinks = self.get(
            f"/data/projects/{self.project_id}/entity-links?limit=100"
        )
        self.assertEqual(len(alllinks), 22)

        url = f"/data/projects/{self.project_id}/entity-links"
        query = f"?cursor_created_at={alllinks[9]['created_at']}&limit=10"
        links = self.get(url + query)["data"]
        self.assertEqual(len(links), 10)
        query = f"?cursor_created_at={links[9]['created_at']}&limit=10"
        links = self.get(url + query)["data"]
        self.assertEqual(len(links), 2)
        self.assertEqual(links[1]["id"], alllinks[21]["id"])
