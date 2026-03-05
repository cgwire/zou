from tests.base import ApiDBTestCase

from zou.app.models.milestone import Milestone
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
)
from zou.app.services import schedule_service
from zou.app.services.exception import (
    ProductionScheduleVersionNotFoundException,
)


class ScheduleServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(ScheduleServiceTestCase, self).setUp()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.sequence_id = str(self.sequence.id)
        self.episode_id = str(self.episode.id)
        self.asset_type_id = str(self.asset_type.id)

    def test_get_schedule_items(self):
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 1)
        self.generate_fixture_shot_task()
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 2)
        task_type_ids = [item["task_type_id"] for item in items]
        self.assertTrue(str(self.task_type.id) in task_type_ids)
        self.assertTrue(str(self.task_type_animation.id) in task_type_ids)

        self.shot_task.delete()
        items = schedule_service.get_task_types_schedule_items(self.project.id)
        self.assertEqual(len(items), 1)

    def test_get_schedule_sequence_items(self):
        items = schedule_service.get_sequences_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.sequence_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_episode_items(self):
        items = schedule_service.get_episodes_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(items[0]["object_id"], self.episode_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_asset_type_items(self):
        items = schedule_service.get_asset_types_schedule_items(
            self.project.id, self.task_type_id
        )
        self.assertEqual(items[0]["object_id"], self.asset_type_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_all_schedule_items(self):
        schedule_service.get_task_types_schedule_items(self.project.id)
        items = schedule_service.get_schedule_items(self.project.id)
        self.assertGreater(len(items), 0)

    def test_get_milestones_for_project(self):
        milestones = schedule_service.get_milestones_for_project(
            self.project_id
        )
        self.assertEqual(len(milestones), 0)

        Milestone.create(
            name="Alpha",
            project_id=self.project.id,
            date="2024-06-01",
        )
        Milestone.create(
            name="Beta",
            project_id=self.project.id,
            date="2024-09-01",
        )
        milestones = schedule_service.get_milestones_for_project(
            self.project_id
        )
        self.assertEqual(len(milestones), 2)

    def test_get_production_schedule_version_raw(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.get_production_schedule_version_raw(
            str(psv.id)
        )
        self.assertEqual(result.id, psv.id)

    def test_get_production_schedule_version_raw_not_found(self):
        with self.assertRaises(
            ProductionScheduleVersionNotFoundException
        ):
            schedule_service.get_production_schedule_version_raw(
                "wrong-id"
            )

    def test_get_production_schedule_version(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.get_production_schedule_version(
            str(psv.id)
        )
        self.assertEqual(result["id"], str(psv.id))
        self.assertEqual(result["name"], "v1")

    def test_update_production_schedule_version(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        result = schedule_service.update_production_schedule_version(
            str(psv.id), {"name": "v2"}
        )
        self.assertEqual(result["name"], "v2")

    def test_get_production_schedule_version_task_links(self):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        links = (
            schedule_service.get_production_schedule_version_task_links(
                str(psv.id)
            )
        )
        self.assertEqual(len(links), 0)

    def test_set_production_schedule_version_task_links_from_production(
        self,
    ):
        psv = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        links = schedule_service.set_production_schedule_version_task_links_from_production(
            str(psv.id)
        )
        self.assertGreater(len(links), 0)
