from tests.base import ApiDBTestCase
from zou.app.models.status_automation import StatusAutomation

from zou.app.utils import fields


class StatusAutomationTestCase(ApiDBTestCase):
    def setUp(self):
        super(StatusAutomationTestCase, self).setUp()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_wip()
        self.generate_data(
            StatusAutomation,
            1,
            entity_type="asset",
            in_task_type_id=self.task_type_concept.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )
        self.generate_data(
            StatusAutomation,
            1,
            entity_type="asset",
            in_task_type_id=self.task_type_modeling.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="ready_for",
            out_task_type_id=self.task_type_layout.id,
        )

    def test_get_status_automations(self):
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 2)

    def test_get_status_automation(self):
        status_automation = self.get_first("data/status-automations")
        status_automation_again = self.get(
            "data/status-automations/%s" % status_automation["id"]
        )
        self.assertEqual(status_automation, status_automation_again)
        self.get_404("data/status-automations/%s" % fields.gen_uuid())

    def test_create_status_automation(self):
        data = {
            "entity_type": "asset",
            "in_task_type_id": self.task_type_concept.id,
            "in_task_status_id": self.task_status_done.id,
            "out_field_type": "status",
            "out_task_type_id": self.task_type_modeling.id,
            "out_task_status_id": self.task_status_wip.id,
        }
        self.status_automation = self.post("data/status-automations", data)
        self.assertIsNotNone(self.status_automation["id"])

        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 3)

    def test_update_status_automation(self):
        status_automation = self.get_first("data/status-automations")
        data = {"out_field_type": "ready_for"}
        self.put("data/status-automations/%s" % status_automation["id"], data)
        status_automation_again = self.get(
            "data/status-automations/%s" % status_automation["id"]
        )
        self.assertEqual(
            data["out_field_type"], status_automation_again["out_field_type"]
        )
        self.put_404("data/status-automations/%s" % fields.gen_uuid(), data)

    def test_delete_status_automation(self):
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 2)
        status_automation = status_automations[0]
        self.delete("data/status-automations/%s" % status_automation["id"])
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 1)
        self.delete_404("data/status-automations/%s" % fields.gen_uuid())
