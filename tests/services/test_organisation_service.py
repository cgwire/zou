from zou.app.services import organisation_service
from tests.services.cases import PersonsTestCase


class OrganisationTestCase(PersonsTestCase):
    """
    The single organisation row of the instance.
    """

    def test_get_organisation(self):
        organisation = organisation_service.get_organisation()
        self.assertIn("id", organisation)

    def test_get_organisation_creates_it_once(self):
        """
        A fresh instance has no organisation row: the first reading makes
        it, and every later one finds it.
        """
        self.assertEqual(
            organisation_service.get_organisation()["id"],
            organisation_service.get_organisation()["id"],
        )

    def test_update_organisation(self):
        organisation = organisation_service.get_organisation()
        result = organisation_service.update_organisation(
            organisation["id"], {"name": "NewOrg"}
        )
        self.assertEqual(result["name"], "NewOrg")
        # Read back through the memoized path, which the update has to drop.
        self.assertEqual(
            organisation_service.get_organisation()["name"], "NewOrg"
        )
