from tests.base import ApiDBTestCase


class AssetTypesTestCase(ApiDBTestCase):
    def setUp(self):
        super(AssetTypesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_asset_types(self):
        asset_types = self.get("data/asset-types")
        self.assertEqual(len(asset_types), 1)
        self.assertDictEqual(
            asset_types[0],
            self.asset_type.serialize(obj_type="AssetType", relations=True),
        )

    def test_get_entity_types(self):
        asset_types = self.get("data/entity-types?name=Props&relations=true")
        self.assertEqual(len(asset_types), 1)
        asset_types[0]["type"] = "AssetType"
        self.assertDictEqual(
            asset_types[0],
            self.asset_type.serialize(obj_type="AssetType", relations=True),
        )

    def test_get_asset_type(self):
        asset_type = self.get(f"data/asset-types/{self.asset_type.id}")
        self.assertDictEqual(
            asset_type,
            self.asset_type.serialize(obj_type="AssetType", relations=True),
        )

    def test_get_project_asset_types(self):
        asset_types = self.get(f"data/projects/{self.project.id}/asset-types")
        self.assertEqual(len(asset_types), 1)
        self.assertDictEqual(
            asset_types[0], self.asset_type.serialize(obj_type="AssetType")
        )

    def test_get_shot_asset_types(self):
        asset_types = self.get(f"data/shots/{self.shot.id}/asset-types")
        self.assertEqual(len(asset_types), 0)

        self.shot.entities_out = [self.asset]
        self.shot.save()

        asset_types = self.get(f"data/shots/{self.shot.id}/asset-types")
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["type"], "AssetType")
