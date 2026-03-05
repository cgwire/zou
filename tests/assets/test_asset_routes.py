from tests.base import ApiDBTestCase

from zou.app.services import breakdown_service


class AssetRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(AssetRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()
        self.project_id = str(self.project.id)
        self.asset_id = str(self.asset.id)
        self.shot_id = str(self.shot.id)

    def _set_casting(self):
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting",
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )

    def test_get_asset_casting(self):
        result = self.get(f"/data/assets/{self.asset_id}/casting")
        self.assertIsInstance(result, list)

    def test_update_asset_casting(self):
        result = self.put(
            f"/data/assets/{self.asset_id}/casting",
            [
                {
                    "asset_id": str(self.asset_character.id),
                    "nb_occurences": 2,
                }
            ],
        )
        self.assertIsInstance(result, list)

    def test_get_asset_cast_in(self):
        self._set_casting()
        result = self.get(f"/data/assets/{self.asset_id}/cast-in")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_get_asset_shot_asset_instances(self):
        result = self.get(
            f"/data/assets/{self.asset_id}/shot-asset-instances"
        )
        self.assertIsInstance(result, list)

    def test_get_asset_scene_asset_instances(self):
        result = self.get(
            f"/data/assets/{self.asset_id}/scene-asset-instances"
        )
        self.assertIsInstance(result, list)

    def test_get_asset_asset_instances(self):
        result = self.get(
            f"/data/assets/{self.asset_id}/asset-asset-instances"
        )
        self.assertIsInstance(result, list)

    def test_create_asset_asset_instance(self):
        result = self.post(
            f"/data/assets/{self.asset_id}/asset-asset-instances",
            {
                "asset_to_instantiate_id": str(self.asset_character.id),
                "description": "Instance in asset",
            },
        )
        self.assertIsNotNone(result.get("id"))

    def test_get_asset_assets(self):
        result = self.get(f"/data/assets/{self.asset_id}/assets")
        self.assertIsInstance(result, list)

    def test_share_assets(self):
        result = self.post(
            "/actions/assets/share",
            {
                "asset_ids": [self.asset_id],
                "is_shared": True,
            },
            200,
        )
        self.assertIsInstance(result, dict)

    def test_share_project_assets(self):
        result = self.post(
            f"/actions/projects/{self.project_id}/assets/share",
            {"is_shared": True},
            200,
        )
        self.assertIsInstance(result, dict)

    def test_share_project_asset_type_assets(self):
        result = self.post(
            f"/actions/projects/{self.project_id}"
            f"/asset-types/{self.asset_type.id}/assets/share",
            {"is_shared": True},
            200,
        )
        self.assertIsInstance(result, dict)

    def test_get_project_shared_used_assets(self):
        result = self.get(
            f"/data/projects/{self.project_id}/assets/shared-used"
        )
        self.assertIsInstance(result, list)

    def test_get_project_episode_shared_used_assets(self):
        self.generate_fixture_episode()
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode.id}/assets/shared-used"
        )
        self.assertIsInstance(result, list)
