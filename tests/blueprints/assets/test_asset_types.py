from tests.base import ApiDBTestCase


class AssetTypesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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

    def test_get_asset_types_filtered_by_name(self):
        """
        A criterion is read off the asset types themselves. Built against
        the asset table instead, the two cross joined and the name of a
        type matched no asset, so the listing came back empty.
        """
        self.generate_fixture_asset_types()
        asset_types = self.get("data/asset-types?name=Character")
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Character"]
        )

    def test_get_asset_types_filtered_by_project(self):
        """
        A production is not a column of the asset type table: the criterion
        the route documents is which types the production has assets of.
        Handed to the generic criterion helper it restricted nothing.
        """
        self.generate_fixture_asset_types()
        self.generate_fixture_project_standard()
        self.generate_fixture_asset(
            "Elsewhere",
            asset_type_id=self.asset_type_character.id,
            project_id=self.project_standard.id,
        )
        asset_types = self.get(
            f"data/asset-types?project_id={self.project.id}"
        )
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
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
        self.assertEqual(asset_types, [])

        self.shot.entities_out = [self.asset]
        self.shot.save()

        asset_types = self.get(f"data/shots/{self.shot.id}/asset-types")
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["type"], "AssetType")
