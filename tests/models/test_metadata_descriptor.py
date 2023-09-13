from tests.base import ApiDBTestCase

from zou.app.utils import fields
from zou.app.models.metadata_descriptor import MetadataDescriptor


class MetadataTestCase(ApiDBTestCase):
    def setUp(self):
        super(MetadataTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_metadata_descriptor()

    def test_get_metadata_descriptors(self):
        descriptors = self.get("data/metadata-descriptors")
        self.assertEqual(len(descriptors), 1)

    def test_get_metadata_descriptor(self):
        descriptor = self.get_first("data/metadata-descriptors")
        descriptor_again = self.get(
            "data/metadata-descriptors/%s" % descriptor["id"]
        )
        self.assertEqual(descriptor, descriptor_again)
        self.get_404("data/metadata-descriptor/%s" % fields.gen_uuid())

    def test_create_metadata_descriptor(self):
        data = {
            "name": "Descriptor test",
            "field_name": "descriptor-test",
            "data_type": "string",
            "entity_type": "Asset",
            "project_id": self.project.id,
        }
        descriptor = self.post("data/metadata-descriptors", data)
        self.assertIsNotNone(descriptor["id"])
        descriptors = self.get("data/metadata-descriptors")
        self.assertEqual(len(descriptors), 2)
        data = {
            "name": "Descriptor test 2",
            "field_name": "descriptor-test",
            "data_type": "wrongdatatype",
            "entity_type": "Asset",
            "project_id": self.project.id,
        }
        descriptor = self.post("data/metadata-descriptors", data, 400)

    def test_update_metadatad_descriptor(self):
        descriptor = self.get_first("data/metadata-descriptors")
        data = {"name": "Descriptor test update"}
        self.put("data/metadata-descriptors/%s" % descriptor["id"], data)
        descriptor_again = self.get(
            "data/metadata-descriptors/%s" % descriptor["id"]
        )
        self.assertEqual(data["name"], descriptor_again["name"])
        self.put_404("data/metadata-descriptors/%s" % fields.gen_uuid(), data)
        data = {"data_type": "wrongdatatype"}
        self.put("data/metadata-descriptors/%s" % descriptor["id"], data, 400)

    def test_delete_metadadescriptor(self):
        descriptors = self.get("data/metadata-descriptors")
        self.assertEqual(len(descriptors), 1)
        descriptor = descriptors[0]
        self.delete("data/metadata-descriptors/%s" % descriptor["id"])
        self.assertIsNone(MetadataDescriptor.get(descriptor["id"]))
        self.delete("data/metadata-descriptors/%s" % fields.gen_uuid(), 404)
