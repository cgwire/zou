from tests.base import ApiDBTestCase

from zou.app.services import (
    assets_service,
    breakdown_service,
    projects_service,
    tasks_service,
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
        self.put("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.episode_id
        ), new_casting)
        casting = self.get("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.episode_id
        ))
        self.assertEquals(len(casting), 2)
        self.assertEquals(casting[0]["asset_name"], "Rabbit")
        self.assertEquals(casting[1]["asset_name"], "Tree")

    def test_get_shot_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.shot_id
        ), new_casting)
        casting = self.get("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.shot_id
        ))
        self.assertEquals(len(casting), 2)
        self.assertEquals(casting[0]["asset_name"], "Rabbit")
        self.assertEquals(casting[1]["asset_name"], "Tree")

        # Test automatic addition to related episode
        casting = self.get("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.episode_id
        ))
        self.assertEquals(len(casting), 2)
        self.assertEquals(casting[0]["asset_name"], "Rabbit")
        self.assertEquals(casting[1]["asset_name"], "Tree")

    def test_remove_from_episode_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.shot_id
        ), new_casting)

        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
        ]
        self.put("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.episode_id
        ), new_casting)

        casting = self.get("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.episode_id
        ))
        self.assertEquals(len(casting), 1)
        casting = self.get("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.shot_id
        ))
        self.assertEquals(len(casting), 1)
        self.assertEquals(casting[0]["asset_name"], "Tree")

    def test_get_episode_assets(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        self.put("/data/projects/%s/entities/%s/casting" % (
            self.project_id,
            self.shot_id
        ), new_casting)
        assets = self.get("/data/assets?episode_id=%s" % self.episode_id)
        assets = sorted(assets, key=lambda a: a["name"])
        self.assertEquals(len(assets), 2)
        self.assertEquals(assets[0]["name"], "Rabbit")
        self.assertEquals(assets[1]["name"], "Tree")

        self.asset.update({"source_id": self.episode_id})
        assets = self.get("/data/assets?episode_id=%s" % self.episode_id)
        self.assertEquals(len(assets), 3)
