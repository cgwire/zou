from tests.base import ApiDBTestCase

from zou.app.services import projects_service
from zou.app.utils import fields


class ScheduleItemTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_schedule_item(self.task_type)
        self.generate_fixture_schedule_item(self.task_type_animation)
        self.generate_fixture_schedule_item(self.task_type_layout)

    def test_get_schedule_items(self):
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 3)

    def test_get_schedule_item(self):
        schedule_items = self.get_first("data/schedule-items")
        schedule_items_again = self.get(
            f"data/schedule-items/{schedule_items['id']}"
        )
        self.assertEqual(schedule_items, schedule_items_again)
        self.get_404(f"data/schedule-items/{fields.gen_uuid()}")

    def test_create_schedule_items(self):
        self.generate_fixture_sequence()
        project_id = str(self.project.id)
        task_type_id = str(self.task_type.id)
        data = {
            "project_id": project_id,
            "task_type_id": task_type_id,
            "object_id": self.sequence.id,
        }
        self.schedule_items = self.post("data/schedule-items", data)
        self.assertIsNotNone(self.schedule_items["id"])
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 4)
        data = {"project_id": project_id, "task_type_id": task_type_id}
        self.schedule_items = self.post("data/schedule-items", data, 400)

    def test_update_schedule_items(self):
        schedule_items = self.get_first("data/schedule-items")
        data = {"man_days": 3}
        self.put(f"data/schedule-items/{schedule_items['id']}", data)
        schedule_items_again = self.get(
            f"data/schedule-items/{schedule_items['id']}"
        )
        self.assertEqual(data["man_days"], schedule_items_again["man_days"])
        self.put_404(f"data/schedule-items/{fields.gen_uuid()}", data)

    def test_delete_schedule_items(self):
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 3)
        schedule_items = schedule_items[0]
        self.delete(f"data/schedule-items/{schedule_items['id']}")
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 2)
        self.delete_404(f"data/schedule-items/{fields.gen_uuid()}")

    def _entity_bar_data(self):
        return {
            "project_id": str(self.project.id),
            "task_type_id": str(self.task_type.id),
            "object_id": str(self.asset_type.id),
        }

    def test_project_manager_can_add_and_remove_a_bar(self):
        # Adding or removing a task type is open to the managers of the
        # production, a manager role held on this production only included:
        # its bar follows.
        artist = self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            str(self.project.id), artist["id"], role="manager"
        )
        self.log_in_cg_artist()
        created = self.post("data/schedule-items", self._entity_bar_data())
        self.delete(f"data/schedule-items/{created['id']}")
        self.delete(f"data/schedule-items/{self.schedule_item.id}")

    def test_supervisor_cannot_add_or_remove_a_bar(self):
        supervisor = self.generate_fixture_user_supervisor()
        projects_service.add_team_member(
            str(self.project.id), supervisor["id"]
        )
        self.log_in_supervisor()
        self.post("data/schedule-items", self._entity_bar_data(), 403)
        self.delete(f"data/schedule-items/{self.schedule_item.id}", 403)
