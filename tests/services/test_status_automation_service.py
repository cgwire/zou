# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase

from zou.app.services import (
    comments_service,
    status_automations_service,
    tasks_service,
)


class StatusAutomationServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(StatusAutomationServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_asset_type()
        self.entity = self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.task_concept = self.generate_fixture_task(
            name="Concept",
            entity_id=self.entity.id,
            task_type_id=self.task_type_concept.id,
        )
        self.task_modeling = self.generate_fixture_task(
            name="Modeling",
            entity_id=self.entity.id,
            task_type_id=self.task_type_modeling.id,
        )
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_done()
        self.generate_fixture_status_automation_to_status()
        self.generate_fixture_status_automation_to_ready_for()

    def test_created_status_automation(self):
        self.assertEqual(
            len(status_automations_service.get_status_automations()), 2
        )

    def test_status_automation_to_status(self):
        wip_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc"
        )
        comments_service.create_comment(
            self.person.id,
            self.task_concept.id,
            str(self.task_status_done.id),
            "Test",
            [],
            {},
            None,
        )
        self.assertEqual(
            str(self.task_modeling.task_status_id), wip_status["id"]
        )

    def test_status_automation_to_ready_for(self):
        comments_service.create_comment(
            self.person.id,
            self.task_modeling.id,
            str(self.task_status_done.id),
            "Test",
            [],
            {},
            None,
        )
        self.assertEqual(self.asset.ready_for, self.task_type_layout.id)
