import json

from tests.base import ApiDBTestCase
from zou.app.models.status_automation import StatusAutomation
from zou.app.services import project_templates_service, projects_service
from zou.app.utils import fields

OUT_FIELD_TYPE_ERROR = "out_field_type must be 'status' or 'ready_for'."


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

    def condition(self, task_type, *task_statuses):
        return {
            "task_type_id": str(task_type.id),
            "task_status_ids": [
                str(task_status.id) for task_status in task_statuses
            ],
        }

    def automation_data(self, **extra):
        return {
            "entity_type": "asset",
            "in_conditions": {
                "operator": "and",
                "conditions": [
                    self.condition(
                        self.task_type_concept, self.task_status_done
                    )
                ],
            },
            "out_field_type": "status",
            "out_task_type_id": self.task_type_modeling.id,
            "out_task_status_id": self.task_status_wip.id,
            **extra,
        }

    def test_get_status_automations(self):
        status_automations = self.get("data/status-automations")
        self.assertEqual(len(status_automations), 2)
        self.assertIn("in_conditions", status_automations[0])

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
        self.assertEqual(
            self.status_automation["in_conditions"],
            {
                "operator": "and",
                "conditions": [
                    self.condition(
                        self.task_type_concept, self.task_status_done
                    )
                ],
            },
        )

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

    def test_create_status_automation_with_conditions(self):
        self.generate_fixture_task_status_retake()
        data = {
            "entity_type": "asset",
            "in_conditions": {
                "operator": "and",
                "conditions": [
                    self.condition(
                        self.task_type_concept, self.task_status_done
                    ),
                    self.condition(
                        self.task_type,
                        self.task_status_done,
                        self.task_status_retake,
                    ),
                ],
            },
            "out_field_type": "status",
            "out_task_type_id": self.task_type_modeling.id,
            "out_task_status_id": self.task_status_wip.id,
        }

        automation = self.post("data/status-automations", data)

        self.assertEqual(
            automation["in_conditions"],
            fields.serialize_value(data["in_conditions"]),
        )
        self.assertIsNone(automation["in_task_type_id"])
        self.assertIsNone(automation["in_task_status_id"])

    def test_create_invalid_status_automation(self):
        concept_done = self.condition(
            self.task_type_concept, self.task_status_done
        )
        data = {
            "entity_type": "asset",
            "in_conditions": {
                "operator": "and",
                "conditions": [
                    {"operator": "or", "conditions": [concept_done]}
                ],
            },
            "out_field_type": "status",
            "out_task_type_id": self.task_type_modeling.id,
            "out_task_status_id": self.task_status_wip.id,
        }

        result = self.post("data/status-automations", data, 400)

        self.assertEqual(
            result["message"], "Condition groups are not supported yet."
        )
        self.assertEqual(len(self.get("data/status-automations")), 2)

    def test_create_status_automation_from_a_body_that_is_no_object(self):
        for body in ([{"entity_type": "asset"}], "an id", 5, True):
            with self.subTest(body=body):
                result = self.post("data/status-automations", body, 400)

                self.assertEqual(
                    result["message"], "A JSON object is expected."
                )
        self.assertEqual(len(self.get("data/status-automations")), 2)

    def test_update_status_automation_from_a_body_that_is_no_object(self):
        automation = self.get("data/status-automations")[0]
        for body in ([{"archived": True}], "an id", 5, True):
            with self.subTest(body=body):
                result = self.put(
                    f"data/status-automations/{automation['id']}", body, 400
                )

                self.assertEqual(
                    result["message"], "A JSON object is expected."
                )

    def test_create_status_automation_with_an_unknown_output_type(self):
        for out_field_type in ("foo", "Status", "", None, ["status"], 5):
            with self.subTest(out_field_type=out_field_type):
                result = self.post(
                    "data/status-automations",
                    self.automation_data(out_field_type=out_field_type),
                    400,
                )

                self.assertEqual(result["message"], OUT_FIELD_TYPE_ERROR)
        self.assertEqual(StatusAutomation.query.count(), 2)

    def test_create_status_automation_without_an_output_type(self):
        data = self.automation_data()
        del data["out_field_type"]

        automation = self.post("data/status-automations", data)

        self.assertEqual(automation["out_field_type"], "status")

    def test_update_status_automation_with_an_unknown_output_type(self):
        automation = self.get_first("data/status-automations")
        path = f"data/status-automations/{automation['id']}"
        for out_field_type in ("foo", "Status", "", None, ["status"], 5):
            with self.subTest(out_field_type=out_field_type):
                result = self.put(
                    path, {"out_field_type": out_field_type}, 400
                )

                self.assertEqual(result["message"], OUT_FIELD_TYPE_ERROR)
        self.assertEqual(
            self.get(path)["out_field_type"], automation["out_field_type"]
        )

    def test_archive_a_status_automation_with_an_empty_output_type(self):
        """
        Older releases stored it. Such a row fires nothing, and it stays
        editable as long as the write does not change that value.
        """
        automation = StatusAutomation.create(
            entity_type="asset",
            in_conditions=self.automation_data()["in_conditions"],
            out_field_type="",
            out_task_type_id=self.task_type_modeling.id,
        )

        self.put(
            f"data/status-automations/{automation.id}",
            {"out_field_type": "", "archived": True},
        )

        self.assertTrue(StatusAutomation.get(automation.id).archived)

    def test_create_status_automation_with_an_empty_entity_type(self):
        """
        The runner looks for an entity type of that name: the row would
        never fire.
        """
        for entity_type in ("", None):
            with self.subTest(entity_type=entity_type):
                automation = self.post(
                    "data/status-automations",
                    self.automation_data(entity_type=entity_type),
                )

                self.assertEqual(automation["entity_type"], "asset")

    def test_create_status_automation_without_an_entity_type(self):
        data = self.automation_data()
        del data["entity_type"]

        automation = self.post("data/status-automations", data)

        self.assertEqual(automation["entity_type"], "asset")

    def test_update_status_automation_with_an_empty_entity_type(self):
        automation = self.get_first("data/status-automations")
        path = f"data/status-automations/{automation['id']}"
        for entity_type in ("", None):
            with self.subTest(entity_type=entity_type):
                self.put(path, {"entity_type": entity_type})

                self.assertEqual(self.get(path)["entity_type"], "asset")

    def test_update_status_automation_without_its_entity_type(self):
        automation = StatusAutomation.create(
            entity_type="shot",
            in_conditions={
                "operator": "and",
                "conditions": [
                    self.condition(
                        self.task_type_layout, self.task_status_done
                    )
                ],
            },
            out_field_type="status",
            out_task_type_id=self.task_type_animation.id,
            out_task_status_id=self.task_status_wip.id,
        )

        self.put(
            f"data/status-automations/{automation.id}", {"archived": True}
        )

        self.assertEqual(
            StatusAutomation.get(automation.id).entity_type, "shot"
        )

    def test_give_an_entity_type_to_a_status_automation_breaking_a_rule(self):
        """
        The runner never fires a row with no entity type: the write that
        gives it one is validated.
        """
        group = {
            "operator": "and",
            "conditions": [
                self.condition(self.task_type_layout, self.task_status_done)
            ],
        }
        for stored in (None, ""):
            with self.subTest(stored=stored):
                automation = StatusAutomation.create(
                    in_conditions=group,
                    out_field_type="status",
                    out_task_type_id=self.task_type_modeling.id,
                    out_task_status_id=self.task_status_wip.id,
                )
                automation.update({"entity_type": stored})

                result = self.put(
                    f"data/status-automations/{automation.id}",
                    {"entity_type": "asset", "archived": True},
                    400,
                )

                self.assertIn(
                    "is not a task type of assets", result["message"]
                )
                self.assertEqual(
                    StatusAutomation.get(automation.id).entity_type, stored
                )

    def test_give_an_entity_type_to_a_status_automation(self):
        automation = StatusAutomation.create(
            in_conditions=self.automation_data()["in_conditions"],
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )
        automation.update({"entity_type": None})

        self.put(
            f"data/status-automations/{automation.id}", {"entity_type": ""}
        )

        self.assertEqual(
            StatusAutomation.get(automation.id).entity_type, "asset"
        )

    def test_update_status_automation_conditions(self):
        automation = self.post(
            "data/status-automations",
            {
                "entity_type": "asset",
                "in_task_type_id": self.task_type_concept.id,
                "in_task_status_id": self.task_status_done.id,
                "out_field_type": "status",
                "out_task_type_id": self.task_type_modeling.id,
                "out_task_status_id": self.task_status_wip.id,
            },
        )
        path = f"data/status-automations/{automation['id']}"
        conditions = {
            "operator": "or",
            "conditions": [
                self.condition(self.task_type_concept, self.task_status_done),
                self.condition(self.task_type, self.task_status_done),
            ],
        }

        self.put(path, {"in_conditions": conditions})

        automation_again = self.get(path)
        self.assertEqual(automation_again["in_conditions"], conditions)
        self.assertIsNone(automation_again["in_task_type_id"])
        result = self.put(
            path,
            {
                "in_task_type_id": str(self.task_type_concept.id),
                "in_task_status_id": str(self.task_status_done.id),
            },
            400,
        )
        self.assertEqual(
            result["message"],
            "This automation has several trigger conditions: update it "
            "through in_conditions.",
        )

    def test_archive_a_status_automation_breaking_a_rule(self):
        """
        Kitsu sends the whole form back: a row stored before a rule existed
        must stay editable as long as the write does not change it.
        """
        group = {
            "operator": "and",
            "conditions": [
                self.condition(self.task_type_layout, self.task_status_done)
            ],
        }
        automation = StatusAutomation.create(
            entity_type="asset",
            in_conditions=group,
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )

        self.put(
            f"data/status-automations/{automation.id}",
            {
                "entity_type": "asset",
                "in_conditions": group,
                "out_field_type": "status",
                "out_task_type_id": str(self.task_type_modeling.id),
                "out_task_status_id": str(self.task_status_wip.id),
                "out_only_if_task_status_ids": [],
                "import_last_revision": False,
                "archived": True,
            },
        )

        self.assertTrue(StatusAutomation.get(automation.id).archived)

    def test_archive_a_status_automation_with_an_id_that_is_no_uuid(self):
        """
        A row a sync stored with an id that is not a UUID stays editable,
        its trigger as stored.
        """
        group = {
            "operator": "and",
            "conditions": [
                {
                    "task_type_id": str(self.task_type_concept.id),
                    "task_status_ids": ["not-a-uuid"],
                }
            ],
        }
        automation = StatusAutomation.create(
            entity_type="asset",
            in_conditions=group,
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )

        self.put(
            f"data/status-automations/{automation.id}", {"archived": True}
        )

        stored = StatusAutomation.get(automation.id)
        self.assertTrue(stored.archived)
        self.assertEqual(stored.in_conditions, group)

    def test_archive_a_status_automation_without_conditions(self):
        """
        A row stored with an empty condition list, which only a sync or a
        direct write can create, stays editable.
        """
        automation = StatusAutomation.create(
            entity_type="asset",
            in_conditions={"operator": "and", "conditions": []},
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )

        self.put(
            f"data/status-automations/{automation.id}", {"archived": True}
        )

        self.assertTrue(StatusAutomation.get(automation.id).archived)
