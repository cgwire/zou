from tests.base import ApiDBTestCase

from zou.app.services import index_service


class AssetSearchTestCase(ApiDBTestCase):
    def setUp(self):
        super(AssetSearchTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset_character()
        self.generate_fixture_asset_character("Sprite")
        self.generate_fixture_asset_character("Cat")
        self.generate_fixture_asset_character("Dog")
        self.generate_fixture_asset_character("Fox")
        self.generate_fixture_asset_character("Lémo")
        self.generate_fixture_asset_character("L'ustensile")
        self.project_ids = [str(self.project.id)]
        self.asset_type_id = str(self.asset_type.id)
        index_service.reset_index()

    def create_girafe_asset(self):
        return self.post(
            "data/projects/%s/asset-types/%s/assets/new"
            % (self.project_id, self.asset_type_id),
            {"name": "Girafe", "description": ""},
        )

    def test_search_assets_exact(self):
        assets = self.post("data/search", {"query": "rabbit"}, 200)["assets"]
        self.assertEqual(len(assets), 1)

    def test_search_assets_partial(self):
        assets = self.post("data/search", {"query": "rab"}, 200)["assets"]
        self.assertEqual(len(assets), 1)
        assets = self.post("data/search", {"query": "usten"}, 200)["assets"]
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_creation(self):
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 0)
        self.create_girafe_asset()
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_update(self):
        asset = self.create_girafe_asset()
        assets = index_service.search_assets("girafe")
        self.assertEqual(len(assets), 1)
        self.put("data/entities/%s" % asset["id"], {"name": "Elephant"})
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 0)
        assets = self.post("data/search", {"query": "elephant"}, 200)["assets"]
        self.assertEqual(len(assets), 1)

    def test_search_assets_after_deletion(self):
        asset = self.create_girafe_asset()
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 1)
        self.delete("data/entities/%s" % asset["id"])
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 0)
        asset = self.create_girafe_asset()
        self.delete("data/assets/%s" % asset["id"])
        assets = self.post("data/search", {"query": "girafe"}, 200)["assets"]
        self.assertEqual(len(assets), 0)
