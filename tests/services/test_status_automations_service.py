# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    comments_service,
    projects_service,
    status_automations_service,
    tasks_service,
)
from zou.app.services.exception import StatusAutomationNotFoundException
from zou.app.utils import fields


class StatusAutomationsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
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

    def a_task_type_for(self, entity_kind, name):
        return TaskType.create(
            name=name,
            short_name=name.lower().replace(" ", ""),
            color="#FFFFFF",
            for_entity=entity_kind,
            department_id=self.department.id,
        )

    def a_task_on(self, entity, task_type):
        return Task.create(
            name=task_type.name,
            project_id=self.project.id,
            task_type_id=task_type.id,
            task_status_id=self.task_status.id,
            entity_id=entity.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

    def an_automation(self, entity_type, in_task_type, out_task_type):
        """
        When a task of in_task_type is marked done on an entity of that
        kind, a task of out_task_type on the same entity goes to wip.
        """
        automation = StatusAutomation.create(
            entity_type=entity_type,
            in_task_type_id=in_task_type.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=out_task_type.id,
            out_task_status_id=self.task_status_wip.id,
        )
        projects_service.add_status_automation_setting(
            self.project_id, automation.id
        )
        return automation

    def mark_done(self, task, text="Test"):
        comments_service.create_comment(
            self.person.id,
            task.id,
            str(self.task_status_done.id),
            text,
            [],
            {},
            None,
        )

    def wip_status_id(self):
        return tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )["id"]

    def assert_the_automation_fires_on(self, entity, entity_type, prefix):
        kind = entity_type.capitalize()
        in_type = self.a_task_type_for(kind, f"{prefix} In")
        out_type = self.a_task_type_for(kind, f"{prefix} Out")
        in_task = self.a_task_on(entity, in_type)
        out_task = self.a_task_on(entity, out_type)
        self.an_automation(entity_type, in_type, out_type)

        self.mark_done(in_task)

        self.assertEqual(
            str(Task.get(out_task.id).task_status_id), self.wip_status_id()
        )

    def test_created_status_automation(self):
        self.assertEqual(
            len(status_automations_service.get_status_automations()), 2
        )

    def test_get_status_automation_raw(self):
        automation = status_automations_service.get_status_automations()[0]
        self.assertEqual(
            status_automations_service.get_status_automation_raw(
                automation["id"]
            ).id,
            StatusAutomation.get(automation["id"]).id,
        )
        self.assertRaises(
            StatusAutomationNotFoundException,
            status_automations_service.get_status_automation_raw,
            fields.gen_uuid(),
        )

    def test_status_automation_to_status(self):
        wip_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
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
        self.task_modeling = Task.get(self.task_modeling.id)
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
        self.asset = Entity.get(self.asset.id)
        self.assertEqual(self.asset.ready_for, self.task_type_layout.id)

    def test_status_automation_sequence(self):
        self.assert_the_automation_fires_on(self.sequence, "sequence", "Seq")

    def test_status_automation_episode(self):
        episode = self.generate_fixture_episode()
        self.assert_the_automation_fires_on(episode, "episode", "Ep")

    def test_get_status_automations_is_memoized(self):
        """
        The listing is cached for two minutes, so an automation added after
        it has been read stays out of it until the cache is dropped. That is
        what clear_status_automation_cache is for.
        """
        before = status_automations_service.get_status_automations()
        automation = self.an_automation(
            "asset", self.task_type_concept, self.task_type_modeling
        )

        self.assertEqual(
            status_automations_service.get_status_automations(), before
        )

        status_automations_service.clear_status_automation_cache()
        self.assertIn(
            str(automation.id),
            [
                held["id"]
                for held in status_automations_service.get_status_automations()
            ],
        )

    def test_status_automation_entity_type_mismatch(self):
        """
        Test that an asset automation does NOT fire on a sequence task.
        """
        # An asset automation whose input task type belongs to sequences: a
        # misconfiguration the entity type filter has to catch.
        sequence_type = self.a_task_type_for("Sequence", "Seq Concept")
        task_seq = self.a_task_on(self.sequence, sequence_type)
        self.an_automation("asset", sequence_type, self.task_type_modeling)
        initial_status = str(self.task_modeling.task_status_id)

        self.mark_done(task_seq, "Should not trigger asset automation")

        self.assertEqual(
            str(Task.get(self.task_modeling.id).task_status_id),
            initial_status,
        )
