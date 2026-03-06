from tests.base import ApiDBTestCase
from zou.app.utils import fields


class EntityLinkTestCase(ApiDBTestCase):
    def setUp(self):
        super(EntityLinkTestCase, self).setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_asset_standard()
        self.generate_fixture_sequence()
        self.entity_in_id = str(self.asset.id)
        self.entity_out_id = str(self.asset_standard.id)
        self.sequence_id = str(self.sequence.id)

    def test_get_entity_links(self):
        self.post(
            "data/entity-links",
            {
                "entity_in_id": self.entity_in_id,
                "entity_out_id": self.entity_out_id,
            },
        )
        entity_links = self.get("data/entity-links")
        self.assertEqual(len(entity_links), 1)

    def test_get_entity_link(self):
        entity_link = self.post(
            "data/entity-links",
            {
                "entity_in_id": self.entity_in_id,
                "entity_out_id": self.entity_out_id,
            },
        )
        entity_link_again = self.get(
            "data/entity-links/%s" % entity_link["id"]
        )
        self.assertEqual(entity_link["id"], entity_link_again["id"])
        self.get_404("data/entity-links/%s" % fields.gen_uuid())

    def test_create_entity_link(self):
        data = {
            "entity_in_id": self.entity_in_id,
            "entity_out_id": self.entity_out_id,
            "nb_occurences": 2,
        }
        entity_link = self.post("data/entity-links", data)
        self.assertIsNotNone(entity_link["id"])
        self.assertEqual(entity_link["nb_occurences"], 2)

    def test_update_entity_link(self):
        entity_link = self.post(
            "data/entity-links",
            {
                "entity_in_id": self.entity_in_id,
                "entity_out_id": self.entity_out_id,
            },
        )
        data = {"nb_occurences": 5}
        self.put("data/entity-links/%s" % entity_link["id"], data)
        entity_link_again = self.get(
            "data/entity-links/%s" % entity_link["id"]
        )
        self.assertEqual(
            data["nb_occurences"], entity_link_again["nb_occurences"]
        )
        self.put_404("data/entity-links/%s" % fields.gen_uuid(), data)

    def test_delete_entity_link(self):
        entity_link = self.post(
            "data/entity-links",
            {
                "entity_in_id": self.entity_in_id,
                "entity_out_id": self.entity_out_id,
            },
        )
        self.delete("data/entity-links/%s" % entity_link["id"])
        entity_links = self.get("data/entity-links")
        self.assertEqual(len(entity_links), 0)
        self.delete_404("data/entity-links/%s" % fields.gen_uuid())
