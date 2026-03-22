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
        """Test that a status automation fires for sequence tasks."""
        # Create sequence-specific task types
        task_type_seq_prep = TaskType.create(
            name="Seq Prep",
            short_name="sprep",
            color="#FFFFFF",
            for_entity="Sequence",
            department_id=self.department.id,
        )
        task_type_seq_review = TaskType.create(
            name="Seq Review",
            short_name="srev",
            color="#FFFFFF",
            for_entity="Sequence",
            department_id=self.department.id,
        )

        # Create tasks on the sequence entity
        task_seq_prep = Task.create(
            name="Seq Prep",
            project_id=self.project.id,
            task_type_id=task_type_seq_prep.id,
            task_status_id=self.task_status.id,
            entity_id=self.sequence.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        task_seq_review = Task.create(
            name="Seq Review",
            project_id=self.project.id,
            task_type_id=task_type_seq_review.id,
            task_status_id=self.task_status.id,
            entity_id=self.sequence.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

        # Create automation: when Seq Prep is done, set Seq Review to WIP
        automation = StatusAutomation.create(
            entity_type="sequence",
            in_task_type_id=task_type_seq_prep.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=task_type_seq_review.id,
            out_task_status_id=self.task_status_wip.id,
        )
        projects_service.add_status_automation_setting(
            self.project_id, automation.id
        )

        wip_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )

        # Trigger the automation
        comments_service.create_comment(
            self.person.id,
            task_seq_prep.id,
            str(self.task_status_done.id),
            "Sequence automation test",
            [],
            {},
            None,
        )

        # Verify the target task status was changed
        task_seq_review = Task.get(task_seq_review.id)
        self.assertEqual(
            str(task_seq_review.task_status_id), wip_status["id"]
        )

    def test_status_automation_episode(self):
        """Test that a status automation fires for episode tasks."""
        self.generate_fixture_episode()

        # Create episode-specific task types
        task_type_ep_setup = TaskType.create(
            name="Ep Setup",
            short_name="eps",
            color="#FFFFFF",
            for_entity="Episode",
            department_id=self.department.id,
        )
        task_type_ep_final = TaskType.create(
            name="Ep Final",
            short_name="epf",
            color="#FFFFFF",
            for_entity="Episode",
            department_id=self.department.id,
        )

        # Create tasks on the episode entity
        task_ep_setup = Task.create(
            name="Ep Setup",
            project_id=self.project.id,
            task_type_id=task_type_ep_setup.id,
            task_status_id=self.task_status.id,
            entity_id=self.episode.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )
        task_ep_final = Task.create(
            name="Ep Final",
            project_id=self.project.id,
            task_type_id=task_type_ep_final.id,
            task_status_id=self.task_status.id,
            entity_id=self.episode.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

        # Create automation: when Ep Setup is done, set Ep Final to WIP
        automation = StatusAutomation.create(
            entity_type="episode",
            in_task_type_id=task_type_ep_setup.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=task_type_ep_final.id,
            out_task_status_id=self.task_status_wip.id,
        )
        projects_service.add_status_automation_setting(
            self.project_id, automation.id
        )

        wip_status = tasks_service.get_or_create_status(
            "Work In Progress", "wip", "#3273dc", is_wip=True
        )

        # Trigger the automation
        comments_service.create_comment(
            self.person.id,
            task_ep_setup.id,
            str(self.task_status_done.id),
            "Episode automation test",
            [],
            {},
            None,
        )

        # Verify the target task status was changed
        task_ep_final = Task.get(task_ep_final.id)
        self.assertEqual(
            str(task_ep_final.task_status_id), wip_status["id"]
        )

    def test_status_automation_entity_type_mismatch(self):
        """Test that an asset automation does NOT fire on a sequence task."""
        # Create sequence-specific task types with the SAME names as asset
        # task types to ensure entity_type filtering is doing its job
        task_type_seq_concept = TaskType.create(
            name="Seq Concept",
            short_name="scpt",
            color="#FFFFFF",
            for_entity="Sequence",
            department_id=self.department.id,
        )

        # Create a sequence task using the sequence-specific task type
        task_seq = Task.create(
            name="Seq Concept",
            project_id=self.project.id,
            task_type_id=task_type_seq_concept.id,
            task_status_id=self.task_status.id,
            entity_id=self.sequence.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

        # Create an asset automation that uses this same task type as input
        # (simulating a misconfiguration)
        automation = StatusAutomation.create(
            entity_type="asset",
            in_task_type_id=task_type_seq_concept.id,
            in_task_status_id=self.task_status_done.id,
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=self.task_status_wip.id,
        )
        projects_service.add_status_automation_setting(
            self.project_id, automation.id
        )

        # The modeling task should NOT change because the automation is for
        # assets but the task's entity is a sequence
        initial_status = str(self.task_modeling.task_status_id)

        comments_service.create_comment(
            self.person.id,
            task_seq.id,
            str(self.task_status_done.id),
            "Should not trigger asset automation",
            [],
            {},
            None,
        )

        self.task_modeling = Task.get(self.task_modeling.id)
        self.assertEqual(
            str(self.task_modeling.task_status_id), initial_status
        )

