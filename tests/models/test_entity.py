from tests.base import ApiDBTestCase

from zou.app.utils import fields


class EntityTestCase(ApiDBTestCase):

    def setUp(self):
        super(EntityTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.asset_1_id = str(self.generate_fixture_asset("Asset 1").id)
        self.asset_2_id = str(self.generate_fixture_asset("Asset 2").id)
        self.asset_3_id = str(self.generate_fixture_asset("Asset 3").id)

    def test_get_entities(self):
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 3)
        self.assertEqual(entities[0]["type"], "Asset")

    def test_get_entity(self):
        entity = self.get_first("data/entities?relations=true")
        entity_again = self.get("data/entities/%s" % entity["id"])
        self.assertEqual(entity, entity_again)
        self.get_404("data/entities/%s" % fields.gen_uuid())

    def test_create_entity(self):
        data = {
            "name": "Cosmos Landromat",
            "description": "Video game trailer.",
            "project_id": self.project.id,
            "entity_type_id": self.asset_type.id
        }
        self.asset = self.post("data/entities", data)
        self.assertIsNotNone(self.asset["id"])

        entities = self.get("data/entities")
        self.assertEqual(len(entities), 4)

    def test_update_entity(self):
        entity = self.get_first("data/entities")
        data = {
            "name": "Cosmos Landromat 2",
            "data": {
                "extra_work": True
            }
        }
        self.put("data/entities/%s" % entity["id"], data)
        entity_again = self.get("data/entities/%s" % entity["id"])
        self.assertEqual(entity_again["name"], data["name"])
        self.assertEqual(entity_again["data"], data["data"])

        data = {
            "data": {
                "extra_field": True
            }
        }
        self.put("data/entities/%s" % entity["id"], data)
        entity_again = self.get("data/entities/%s" % entity["id"])
        self.assertEqual(entity_again["data"], {
            "extra_work": True,
            "extra_field": True
        })

        self.put_404("data/entities/%s" % fields.gen_uuid(), data)

    def test_delete_entity(self):
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 3)
        entity = entities[0]
        self.delete("data/entities/%s" % entity["id"])
        entities = self.get("data/entities")
        self.assertEqual(len(entities), 2)
        self.delete_404("data/entities/%s" % fields.gen_uuid())

    def test_delete_entity_link(self):
        entity_link = {
            "entity_in_id": self.asset_1_id,
            "entity_out_id": self.asset_2_id
        }
        entity_link = self.post("data/entity-links", entity_link)
        entity_links = self.get("data/entity-links")
        self.assertEqual(len(entity_links), 1)
        self.delete("data/entity-links/%s" % entity_link["id"])
        entity_links = self.get("data/entity-links")
        self.assertEqual(len(entity_links), 0)
