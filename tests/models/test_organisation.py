from tests.base import ApiDBTestCase
from zou.app.models.organisation import Organisation, SENSITIVE_FIELDS
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
            f"data/organisations/{organisation['id']}"
        )
        self.assertEqual(organisation, organisation_again)
        self.get_404(f"data/organisations/{fields.gen_uuid()}")

    def test_create_organisation(self):
        data = {"name": "Test Org", "hours_by_day": 7.5}
        self.organisation = self.post("data/organisations", data)
        self.assertIsNotNone(self.organisation["id"])
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 4)

    def test_update_organisation(self):
        organisation = self.get_first("data/organisations")
        data = {"hours_by_day": 6.0}
        self.put(f"data/organisations/{organisation['id']}", data)
        organisation_again = self.get(
            f"data/organisations/{organisation['id']}"
        )
        self.assertEqual(
            data["hours_by_day"], organisation_again["hours_by_day"]
        )
        self.put_404(f"data/organisations/{fields.gen_uuid()}", data)

    def test_chat_tokens_are_admin_only(self):
        organisation = Organisation.query.first()
        organisation.update({field: "a-secret" for field in SENSITIVE_FIELDS})
        organisation_id = str(organisation.id)

        listed = self.get_listed_organisation(organisation_id)
        for field in SENSITIVE_FIELDS:
            self.assertEqual(listed[field], "a-secret")

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        listed = self.get_listed_organisation(organisation_id)
        alone = self.get(f"data/organisations/{organisation_id}")
        for field in SENSITIVE_FIELDS:
            self.assertNotIn(field, listed)
            self.assertNotIn(field, alone)

    def test_chat_tokens_are_not_filterable(self):
        # Hiding the tokens from the payload is not enough: filters run
        # before serialization, so they stay answerable by equality.
        organisation = Organisation.query.first()
        organisation.update({field: "a-secret" for field in SENSITIVE_FIELDS})
        total = len(self.get("data/organisations"))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        for field in SENSITIVE_FIELDS:
            organisations = self.get(f"data/organisations?{field}=a-secret")
            self.assertEqual(len(organisations), total)

    def get_listed_organisation(self, organisation_id):
        return next(
            organisation
            for organisation in self.get("data/organisations")
            if organisation["id"] == organisation_id
        )

    def test_delete_organisation(self):
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 3)
        organisation = organisations[0]
        self.delete(f"data/organisations/{organisation['id']}")
        organisations = self.get("data/organisations")
        self.assertEqual(len(organisations), self.initial_count + 2)
        self.delete_404(f"data/organisations/{fields.gen_uuid()}")
