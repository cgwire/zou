from tests.base import ApiDBTestCase
from zou.app.models.project_status import ProjectStatus
from zou.app.utils import dbhelpers


class IsInitTestCase(ApiDBTestCase):
    def test_a_database_without_project_status_is_not_init(self):
        self.assertFalse(dbhelpers.is_init())

    def test_a_studio_with_more_than_two_statuses_is_init(self):
        for name in ["Open", "Closed", "Archived"]:
            ProjectStatus.create(name=name, color="#FFFFFF")

        self.assertTrue(dbhelpers.is_init())
