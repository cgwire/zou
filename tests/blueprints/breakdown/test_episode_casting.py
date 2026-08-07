from tests.base import ApiDBTestCase


class EpisodeCastingTestCase(ApiDBTestCase):
    """
    Casting read and written through the entity routes. An episode has no
    casting of its own: what it answers is the union of the castings of its
    shots, and writing on it removes from those shots.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.project_id = str(self.project.id)
        self.episode_id = str(self.episode.id)
        self.shot_id = str(self.shot.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)
        # Both repoint the fixture they build, so self.shot is SH02 and
        # self.asset is Dog from here on, while the ids above still name
        # the first shot and Tree.
        self.generate_fixture_shot("SH02")
        self.asset = self.generate_fixture_asset_character("Dog")

    def casting_path(self, entity_id):
        return f"/data/projects/{self.project_id}/entities/{entity_id}/casting"

    def set_casting(self, entity_id, casting=None):
        if casting is None:
            casting = [
                {"asset_id": self.asset_id, "nb_occurences": 1},
                {"asset_id": self.asset_character_id, "nb_occurences": 3},
            ]
        self.put(self.casting_path(entity_id), casting)

    def get_casting(self, entity_id):
        return self.get(self.casting_path(entity_id))

    def test_get_episode_casting(self):
        self.assertListEqual(self.get_casting(self.episode_id), [])

        self.set_casting(self.episode_id)

        casting = self.get_casting(self.episode_id)
        self.assertEqual(len(casting), 2)
        self.assertEqual(casting[0]["asset_name"], "Rabbit")
        self.assertEqual(casting[1]["asset_name"], "Tree")

    def test_shot_casting_shows_up_on_its_episode(self):
        self.set_casting(self.shot_id)

        for entity_id in [self.shot_id, self.episode_id]:
            casting = self.get_casting(entity_id)
            self.assertEqual(len(casting), 2)
            self.assertEqual(casting[0]["asset_name"], "Rabbit")
            self.assertEqual(casting[1]["asset_name"], "Tree")

    def test_remove_from_episode_casting(self):
        self.set_casting(self.shot_id)

        # Writing a shorter casting on the episode drops the missing asset
        # from the shots it was cast in.
        self.set_casting(
            self.episode_id,
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )

        self.assertEqual(len(self.get_casting(self.episode_id)), 1)
        casting = self.get_casting(self.shot_id)
        self.assertEqual(len(casting), 1)
        self.assertEqual(casting[0]["asset_name"], "Tree")

    def test_get_episode_assets(self):
        self.set_casting(self.shot_id)

        assets = sorted(
            self.get(f"/data/assets?episode_id={self.episode_id}"),
            key=lambda asset: asset["name"],
        )
        self.assertEqual(
            [asset["name"] for asset in assets], ["Rabbit", "Tree"]
        )

        # An asset that names the episode as its source belongs to it too,
        # cast or not.
        self.asset.update({"source_id": self.episode_id})
        assets = self.get(f"/data/assets?episode_id={self.episode_id}")
        self.assertEqual(len(assets), 3)

    def test_get_project_entity_links(self):
        for i in range(10):
            shot = self.generate_fixture_shot(f"SH00{i}")
            self.set_casting(
                shot.id,
                [
                    {"asset_id": self.asset_id, "nb_occurences": 1},
                    {"asset_id": self.asset_character_id, "nb_occurences": 1},
                ],
            )
        url = f"/data/projects/{self.project_id}/entity-links"
        all_links = self.get(f"{url}?limit=100")
        self.assertEqual(len(all_links), 22)

        # The cursor is the created_at of the last row read.
        query = f"?cursor_created_at={all_links[9]['created_at']}&limit=10"
        links = self.get(url + query)["data"]
        self.assertEqual(len(links), 10)
        query = f"?cursor_created_at={links[9]['created_at']}&limit=10"
        links = self.get(url + query)["data"]
        self.assertEqual(len(links), 2)
        self.assertEqual(links[1]["id"], all_links[21]["id"])
