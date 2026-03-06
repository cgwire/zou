from tests.base import ApiDBTestCase
from zou.app.models.organisation import Organisation
from zou.app.utils import fields


class OrganisationTestCase(ApiDBTestCase):
    def setUp(self):
        super(OrganisationTestCase, self).setUp()
        self.initial_count = len(self.get("data/organisations"))
        self.generate_data(Organisation, 3)

    def test_get_organisations(self):
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 3)

    def test_get_organisation(self):
        organisation = self.get_first("data/organisations")
        organisation_again = self.get(
            "data/organisations/%s" % organisation["id"]
        )
        self.assertEqual(organisation, organisation_again)
        self.get_404("data/organisations/%s" % fields.gen_uuid())

    def test_create_organisation(self):
        data = {"name": "Test Org", "hours_by_day": 7.5}
        self.organisation = self.post("data/organisations", data)
        self.assertIsNotNone(self.organisation["id"])
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 4)

    def test_update_organisation(self):
        organisation = self.get_first("data/organisations")
        data = {"hours_by_day": 6.0}
        self.put("data/organisations/%s" % organisation["id"], data)
        organisation_again = self.get(
            "data/organisations/%s" % organisation["id"]
        )
        self.assertEqual(
            data["hours_by_day"], organisation_again["hours_by_day"]
        )
        self.put_404("data/organisations/%s" % fields.gen_uuid(), data)

    def test_delete_organisation(self):
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 3)
        organisation = organisations[0]
        self.delete("data/organisations/%s" % organisation["id"])
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 2)
        self.delete_404("data/organisations/%s" % fields.gen_uuid())
