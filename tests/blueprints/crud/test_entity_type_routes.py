from tests.base import ApiDBTestCase


class EntityTypeRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_entity_types(self):
        asset_types = self.get("data/entity-types?name=Props&relations=true")
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["id"], str(self.asset_type.id))
