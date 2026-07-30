from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app.services import index_service

# No pytestmark here: unlike test_search.py these tests stub the indexer out,
# so they cover how a search result is presented without a Meilisearch.


class SearchPersonsSerializationTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.person.update(
            {
                "phone": "0600000000",
                "daily_salary": 400,
                "totp_secret": "JBSWY3DPEHPK3PXP",
            }
        )

    def search(self, minimal):
        results = [(str(self.person.id), ["john"])]
        with patch.object(
            index_service, "get_person_index", return_value=None
        ):
            with patch(
                "zou.app.indexer.indexing.search", return_value=results
            ):
                return index_service.search_persons("john", minimal=minimal)[0]

    def test_minimal_hides_the_personal_fields(self):
        person = self.search(minimal=True)
        for field in ["email", "phone", "daily_salary", "expiration_date"]:
            self.assertNotIn(field, person)
        self.assertEqual(person["matched_terms"], ["john"])

    def test_admins_still_get_the_full_record(self):
        person = self.search(minimal=False)
        for field in ["email", "phone", "daily_salary"]:
            self.assertIn(field, person)

    def test_secrets_never_come_out(self):
        for minimal in [True, False]:
            person = self.search(minimal=minimal)
            self.assertNotIn("totp_secret", person)
            self.assertNotIn("password", person)
