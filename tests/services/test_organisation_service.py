from tests.services.cases import PersonsTestCase
from zou.app.models.organisation import Organisation
from zou.app.services import organisation_service


class OrganisationTestCase(PersonsTestCase):
    """
    The single organisation row of the instance.
    """

    def test_get_organisation_creates_it_once(self):
        """
        A fresh instance has no organisation row: the first reading makes
        it, and every later one finds it. The cache is dropped in between,
        else the second reading never reaches the table.
        """
        first = organisation_service.get_organisation()
        organisation_service.clear_organisation_cache()

        self.assertEqual(organisation_service.get_organisation(), first)
        self.assertEqual(Organisation.query.count(), 1)

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
