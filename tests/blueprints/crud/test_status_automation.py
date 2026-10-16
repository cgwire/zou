import json

from tests.base import ApiDBTestCase
from zou.app.models.status_automation import StatusAutomation
from zou.app.services import project_templates_service, projects_service
from zou.app.utils import fields


class StatusAutomationTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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
            f"data/status-automations/{status_automation['id']}"
        )
        self.assertEqual(status_automation, status_automation_again)
        self.get_404(f"data/status-automations/{fields.gen_uuid()}")

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
        self.put(f"data/status-automations/{status_automation['id']}", data)
        status_automation_again = self.get(
            f"data/status-automations/{status_automation['id']}"
        )
        self.assertEqual(
            data["out_field_type"], status_automation_again["out_field_type"]
        )
        self.put_404(f"data/status-automations/{fields.gen_uuid()}", data)

    def test_delete_status_automation(self):
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 2)
        status_automation = status_automations[0]
        self.delete(f"data/status-automations/{status_automation['id']}")
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 1)
        self.delete_404(f"data/status-automations/{fields.gen_uuid()}")

    def test_delete_status_automation_used_by_a_project(self):
        status_automation = self.get_first("data/status-automations")
        self.generate_fixture_project()
        projects_service.add_status_automation_setting(
            self.project.id, status_automation["id"]
        )

        result = json.loads(
            self.delete(
                f"data/status-automations/{status_automation['id']}", 400
            )
        )

        self.assertEqual(
            result["message"], "This automation is used in a project."
        )
        self.assertEqual(len(self.get("data/status-automations")), 2)

    def test_delete_status_automation_used_by_a_template(self):
        """
        The template link has no delete rule: the deletion used to fail on
        the foreign key and answer with the raw database error.
        """
        status_automation = self.get_first("data/status-automations")
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        project_templates_service.add_status_automation_to_template(
            template["id"], status_automation["id"]
        )

        result = json.loads(
            self.delete(
                f"data/status-automations/{status_automation['id']}", 400
            )
        )

        self.assertEqual(
            result["message"],
            "This automation is used in a project template.",
        )
        self.assertEqual(len(self.get("data/status-automations")), 2)
