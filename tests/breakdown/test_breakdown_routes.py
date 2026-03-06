from tests.base import ApiDBTestCase

from zou.app.services import breakdown_service


class BreakdownRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(BreakdownRoutesTestCase, self).setUp()
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
        self.sequence_id = str(self.sequence.id)
        self.shot_id = str(self.shot.id)
        self.scene_id = str(self.scene.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

    def _set_shot_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 2},
        ]
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting",
            new_casting,
        )

    def test_get_asset_type_casting(self):
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.asset_character_id}/casting",
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/asset-types/{self.asset_type_character.id}/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertIn(self.asset_character_id, result)

    def test_get_episodes_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}/episodes/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(len(result) > 0)

    def test_get_sequence_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/sequences/{self.sequence_id}/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertIn(self.shot_id, result)

    def test_get_episode_sequences_all_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode_id}/sequences/all/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(len(result) > 0)

    def test_get_sequences_all_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}/sequences/all/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertTrue(len(result) > 0)

    def test_delete_entity_link(self):
        self._set_shot_casting()
        links = self.get(
            f"/data/projects/{self.project_id}/entity-links?limit=100"
        )
        initial_count = len(links)
        self.assertTrue(initial_count > 0)
        link_id = links[0]["id"]
        self.delete(
            f"/data/projects/{self.project_id}/entity-links/{link_id}",
            200,
        )
        links_after = self.get(
            f"/data/projects/{self.project_id}/entity-links?limit=100"
        )
        self.assertEqual(len(links_after), initial_count - 1)

    def test_get_scene_asset_instances(self):
        result = self.get(
            f"/data/scenes/{self.scene_id}/asset-instances"
        )
        self.assertIsInstance(result, dict)

    def test_create_scene_asset_instance(self):
        result = self.post(
            f"/data/scenes/{self.scene_id}/asset-instances",
            {
                "asset_id": self.asset_id,
                "description": "Test instance",
            },
        )
        self.assertIsNotNone(result.get("id"))
        instances = self.get(
            f"/data/scenes/{self.scene_id}/asset-instances"
        )
        self.assertIn(self.asset_id, instances)

    def test_get_scene_camera_instances(self):
        result = self.get(
            f"/data/scenes/{self.scene_id}/camera-instances"
        )
        self.assertIsInstance(result, dict)

    def test_get_shot_asset_instances(self):
        result = self.get(
            f"/data/shots/{self.shot_id}/asset-instances"
        )
        self.assertIsInstance(result, dict)

    def test_add_asset_instance_to_shot(self):
        self.generate_fixture_scene_asset_instance()
        result = self.post(
            f"/data/shots/{self.shot_id}/asset-instances",
            {"asset_instance_id": str(self.asset_instance.id)},
        )
        self.assertIsNotNone(result.get("id"))
        instances = self.get(
            f"/data/shots/{self.shot_id}/asset-instances"
        )
        self.assertTrue(len(instances) > 0)

    def test_remove_asset_instance_from_shot(self):
        self.generate_fixture_scene_asset_instance()
        self.post(
            f"/data/shots/{self.shot_id}/asset-instances",
            {"asset_instance_id": str(self.asset_instance.id)},
        )
        self.delete(
            f"/data/shots/{self.shot_id}"
            f"/asset-instances/{self.asset_instance.id}"
        )
        instances = self.get(
            f"/data/shots/{self.shot_id}/asset-instances"
        )
        self.assertEqual(len(instances), 0)
