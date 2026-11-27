from tests.base import ApiDBTestCase


class ShotAssetsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_shot_assets(self):
        assets = self.get(f"data/shots/{self.shot.id}/assets")
        self.assertEqual(assets, [])

        self.shot.entities_out = [self.asset]
        self.shot.save()
        assets = self.get(f"data/shots/{self.shot.id}/assets")
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["type"], "Asset")
