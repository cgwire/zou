from tests.base import ApiDBTestCase
from zou.app.utils import fields


class ProductionScheduleVersionTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProductionScheduleVersionTestCase, self).setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        for i in range(3):
            self.post(
                "data/production-schedule-versions",
                {
                    "name": "Version %d" % i,
                    "project_id": self.project_id,
                },
            )

    def _list_url(self):
        return (
            "data/production-schedule-versions"
            "?project_id=%s" % self.project_id
        )

    def test_get_production_schedule_versions(self):
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 3)

    def test_get_production_schedule_version(self):
        version = self.get_first(self._list_url())
        version_again = self.get(
            "data/production-schedule-versions/%s" % version["id"]
        )
        self.assertEqual(version["id"], version_again["id"])
        self.get_404(
            "data/production-schedule-versions/%s" % fields.gen_uuid()
        )

    def test_create_production_schedule_version(self):
        data = {
            "name": "Version 3",
            "project_id": self.project_id,
        }
        version = self.post(
            "data/production-schedule-versions", data
        )
        self.assertIsNotNone(version["id"])
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 4)

    def test_update_production_schedule_version(self):
        version = self.get_first(self._list_url())
        data = {"name": "Updated Version"}
        self.put(
            "data/production-schedule-versions/%s" % version["id"],
            data,
        )
        version_again = self.get(
            "data/production-schedule-versions/%s" % version["id"]
        )
        self.assertEqual(data["name"], version_again["name"])
        self.put_404(
            "data/production-schedule-versions/%s" % fields.gen_uuid(),
            data,
        )

    def test_delete_production_schedule_version(self):
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 3)
        version = versions[0]
        self.delete(
            "data/production-schedule-versions/%s" % version["id"]
        )
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 2)
        self.delete_404(
            "data/production-schedule-versions/%s" % fields.gen_uuid()
        )
