from tests.base import ApiDBTestCase
from zou.app.utils import fields


class ScheduleItemTestCase(ApiDBTestCase):
    def setUp(self):
        super(ScheduleItemTestCase, self).setUp()
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
            "data/schedule-items/%s" % schedule_items["id"]
        )
        self.assertEqual(schedule_items, schedule_items_again)
        self.get_404("data/schedule-items/%s" % fields.gen_uuid())

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
        self.put("data/schedule-items/%s" % schedule_items["id"], data)
        schedule_items_again = self.get(
            "data/schedule-items/%s" % schedule_items["id"]
        )
        self.assertEqual(data["man_days"], schedule_items_again["man_days"])
        self.put_404("data/schedule-items/%s" % fields.gen_uuid(), data)

    def test_delete_schedule_items(self):
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 3)
        schedule_items = schedule_items[0]
        self.delete("data/schedule-items/%s" % schedule_items["id"])
        schedule_items = self.get("data/schedule-items")
        self.assertEqual(len(schedule_items), 2)
        self.delete_404("data/schedule-items/%s" % fields.gen_uuid())
