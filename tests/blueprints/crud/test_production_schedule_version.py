from tests.base import ApiDBTestCase

from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.services import projects_service
from zou.app.utils import fields


class ProductionScheduleVersionTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        for i in range(3):
            self.post(
                "data/production-schedule-versions",
                {
                    "name": f"Version {i}",
                    "project_id": self.project_id,
                },
            )

    def _list_url(self):
        return (
            f"data/production-schedule-versions?project_id={self.project_id}"
        )

    def test_get_production_schedule_versions(self):
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 3)

    def test_get_production_schedule_version(self):
        version = self.get_first(self._list_url())
        version_again = self.get(
            f"data/production-schedule-versions/{version['id']}"
        )
        self.assertEqual(version["id"], version_again["id"])
        self.get_404(f"data/production-schedule-versions/{fields.gen_uuid()}")

    def test_create_production_schedule_version(self):
        data = {
            "name": "Version 3",
            "project_id": self.project_id,
        }
        version = self.post("data/production-schedule-versions", data)
        self.assertIsNotNone(version["id"])
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 4)

    def test_update_production_schedule_version(self):
        version = self.get_first(self._list_url())
        data = {"name": "Updated Version"}
        self.put(
            f"data/production-schedule-versions/{version['id']}",
            data,
        )
        version_again = self.get(
            f"data/production-schedule-versions/{version['id']}"
        )
        self.assertEqual(data["name"], version_again["name"])
        self.put_404(
            f"data/production-schedule-versions/{fields.gen_uuid()}",
            data,
        )

    def test_delete_production_schedule_version(self):
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 3)
        version = versions[0]
        self.delete(f"data/production-schedule-versions/{version['id']}")
        versions = self.get(self._list_url())
        self.assertEqual(len(versions), 2)
        self.delete_404(
            f"data/production-schedule-versions/{fields.gen_uuid()}"
        )

    def test_task_link_list_is_scoped_to_the_project(self):
        self.generate_fixture_asset()
        self.generate_fixture_task()
        version = self.get_first(self._list_url())
        other_project = self.generate_fixture_project_standard()
        other_version = ProductionScheduleVersion.create(
            name="Other", project_id=other_project.id
        )
        link = ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=version["id"],
            task_id=self.task.id,
        )
        ProductionScheduleVersionTaskLink.create(
            production_schedule_version_id=other_version.id,
            task_id=self.task.id,
        )
        path = (
            "data/production-schedule-version-task-links"
            f"?project_id={self.project_id}"
        )

        links = self.get(path)
        self.assertEqual([row["id"] for row in links], [str(link.id)])

        manager = self.generate_fixture_user_manager()
        projects_service.add_team_member(self.project_id, manager["id"])
        self.log_in_manager()
        links = self.get(path)
        self.assertEqual([row["id"] for row in links], [str(link.id)])

    def test_task_link_list_refuses_a_malformed_project_id(self):
        path = "data/production-schedule-version-task-links?project_id="
        self.get(f"{path}not-a-uuid", 400)
        self.get(path, 400)
