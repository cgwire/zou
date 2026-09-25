from tests.base import ApiDBTestCase

from zou.app.utils import fields
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.services import persons_service, projects_service


class MetadataTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_metadata_descriptor()

    def test_get_metadata_descriptors(self):
        descriptors = self.get("data/metadata-descriptors")
        self.assertEqual(len(descriptors), 1)

    def add_published_descriptor(self):
        return projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Delivery", "string", [], True
        )

    def test_a_client_lists_the_published_descriptors_only(self):
        # The read check meant to refuse a vendor returned instead of
        # raising: every member listed all the descriptors of their
        # productions, the ones kept to the studio included.
        published = self.add_published_descriptor()
        client_id = self.generate_fixture_user_client()["id"]
        projects_service.add_team_member(self.project.id, client_id)
        self.log_in_client()

        descriptors = self.get("data/metadata-descriptors")

        self.assertEqual(
            [descriptor["id"] for descriptor in descriptors],
            [published["id"]],
        )
        # The query string filters cannot reach the ones left out.
        descriptors = self.get(
            f"data/metadata-descriptors?project_id={self.project.id}"
            "&field_name=contractor"
        )
        self.assertEqual(descriptors, [])

    def test_a_client_on_the_project_lists_the_published_descriptors(self):
        published = self.add_published_descriptor()
        manager_id = self.generate_fixture_user_manager()["id"]
        projects_service.add_team_member(
            self.project.id, manager_id, role="client"
        )
        self.log_in_manager()

        descriptors = self.get("data/metadata-descriptors")

        self.assertEqual(
            [descriptor["id"] for descriptor in descriptors],
            [published["id"]],
        )

    def test_a_vendor_lists_the_descriptors_of_their_departments(self):
        self.generate_fixture_department()
        theirs = projects_service.add_metadata_descriptor(
            self.project.id,
            "Asset",
            "Rig",
            "string",
            [],
            False,
            [str(self.department.id)],
        )
        projects_service.add_metadata_descriptor(
            self.project.id,
            "Asset",
            "Layout",
            "string",
            [],
            False,
            [str(self.department_animation.id)],
        )
        vendor_id = self.generate_fixture_user_vendor()["id"]
        projects_service.add_team_member(self.project.id, vendor_id)
        persons_service.add_to_department(str(self.department.id), vendor_id)
        self.log_in_vendor()

        descriptors = self.get("data/metadata-descriptors")

        self.assertEqual(
            {descriptor["id"] for descriptor in descriptors},
            {str(self.meta_descriptor.id), theirs["id"]},
        )

    def test_get_metadata_descriptor(self):
        descriptor = self.get_first("data/metadata-descriptors")
        descriptor_again = self.get(
            f"data/metadata-descriptors/{descriptor['id']}"
        )
        self.assertEqual(descriptor, descriptor_again)
        self.get_404(f"data/metadata-descriptor/{fields.gen_uuid()}")

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
        self.put(f"data/metadata-descriptors/{descriptor['id']}", data)
        descriptor_again = self.get(
            f"data/metadata-descriptors/{descriptor['id']}"
        )
        self.assertEqual(data["name"], descriptor_again["name"])
        self.put_404(f"data/metadata-descriptors/{fields.gen_uuid()}", data)
        data = {"data_type": "wrongdatatype"}
        self.put(f"data/metadata-descriptors/{descriptor['id']}", data, 400)

    def test_delete_metadadescriptor(self):
        descriptors = self.get("data/metadata-descriptors")
        self.assertEqual(len(descriptors), 1)
        descriptor = descriptors[0]
        self.delete(f"data/metadata-descriptors/{descriptor['id']}")
        self.assertIsNone(MetadataDescriptor.get(descriptor["id"]))
        self.delete(f"data/metadata-descriptors/{fields.gen_uuid()}", 404)
