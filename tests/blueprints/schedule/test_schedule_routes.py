from tests.base import ApiDBTestCase
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.schedule_item import ScheduleItem
from zou.app.services import projects_service, schedule_service


class ScheduleRoutesTestCase(ApiDBTestCase):
    """
    The guards and the filters the schedule routes add on top of
    schedule_service.
    """

    def setUp(self):
        super().setUp()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)

    def test_schedule_items_route_blocks_vendors(self):
        """
        A schedule lays out the whole production's dates, which a vendor
        has no business reading even when they work on it.
        """
        # get_schedule_items returns the stored rows, it does not create the
        # missing ones the way the task type listing does.
        schedule_item = ScheduleItem.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            object_id=self.sequence.id,
        )
        path = f"/data/projects/{self.project_id}/schedule-items"

        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(schedule_item.id))

        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project_id, self.user_vendor["id"]
        )
        self.log_in_vendor()
        self.get(path, 403)

    def test_get_production_schedule_version_task_links_route(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )

        links = self.get(
            f"/data/production-schedule-versions/{psv.id}/task-links"
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["task_id"], str(self.task.id))

        # The optional filter narrows on the task type of the linked task.
        self.assertEqual(
            len(
                self.get(
                    f"/data/production-schedule-versions/{psv.id}"
                    f"/task-links?task_type_id={self.task_type_id}"
                )
            ),
            1,
        )
        self.assertEqual(
            self.get(
                f"/data/production-schedule-versions/{psv.id}/task-links?task_type_id={self.task_type_animation.id}"
            ),
            [],
        )

    def test_task_links_route_denies_a_client(self):
        """
        A schedule carries dates and assignees the studio does not show to a
        client, so the route turns clients and vendors away even when they
        are on the production.
        """
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()

        self.get(
            f"/data/production-schedule-versions/{psv.id}/task-links", 403
        )

    def test_apply_to_production_route(self):
        """
        The service behind this is tested on its own; the route adds the
        guard, and only a manager of the production may push a schedule back
        onto its tasks.
        """
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        path = (
            f"/actions/production-schedule-versions/{psv.id}"
            f"/apply-to-production"
        )

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.post(path, {}, 403)

        self.log_in_admin()
        result = self.post(path, {}, 200)
        self.assertEqual(result, {"success": True, "task_count": 1})
        self.assertTrue(ProductionScheduleVersion.get(psv.id).locked)

    def test_set_task_links_from_production_route(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        path = (
            f"/actions/production-schedule-versions/{psv.id}"
            f"/set-task-links-from-production"
        )

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.post(path, {}, 403)

        self.log_in_admin()
        self.post(path, {}, 200)
        self.assertEqual(
            len(
                ProductionScheduleVersionTaskLink.get_all_by(
                    production_schedule_version_id=psv.id
                )
            ),
            1,
        )
