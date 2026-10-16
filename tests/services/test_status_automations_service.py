# -*- coding: UTF-8 -*-
import datetime
from unittest import mock

from flask import current_app
from sqlalchemy import text

from tests.base import ApiDBTestCase
from zou.app import db
from zou.app.exceptions import (
    StatusAutomationNotFoundException,
    WrongParameterException,
)
from zou.app.models.comment import Comment
from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task import Task
from zou.app.models.task_status import TaskStatus
from zou.app.models.task_type import TaskType
from zou.app.services import (
    assets_service,
    comments_service,
    projects_service,
    status_automations_service,
    task_types_service,
    tasks_service,
)
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
        return task_types_service.get_or_create_task_status(
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

    def ids_using_task_type(self, task_type):
        service = status_automations_service
        automations = service.get_automations_using_task_type(task_type.id)
        return sorted(automation["id"] for automation in automations)

    def ids_using_task_status(self, task_status):
        service = status_automations_service
        automations = service.get_automations_using_task_status(task_status.id)
        return sorted(automation["id"] for automation in automations)

    def test_get_automations_using_task_type(self):
        """
        Both ends of an automation count, archived automations too.
        """
        self.status_automation_to_status.update({"archived": True})
        to_status = str(self.status_automation_to_status.id)
        to_ready_for = str(self.status_automation_to_ready_for.id)

        self.assertEqual(
            self.ids_using_task_type(self.task_type_concept), [to_status]
        )
        self.assertEqual(
            self.ids_using_task_type(self.task_type_modeling),
            sorted([to_status, to_ready_for]),
        )
        self.assertEqual(
            self.ids_using_task_type(self.task_type_layout), [to_ready_for]
        )
        self.assertEqual(
            self.ids_using_task_type(self.task_type_animation), []
        )

    def test_get_automations_using_task_status(self):
        to_status = str(self.status_automation_to_status.id)
        to_ready_for = str(self.status_automation_to_ready_for.id)

        self.assertEqual(
            self.ids_using_task_status(self.task_status_done),
            sorted([to_status, to_ready_for]),
        )
        self.assertEqual(
            self.ids_using_task_status(self.task_status_wip), [to_status]
        )
        self.assertEqual(self.ids_using_task_status(self.task_status), [])

    def test_guard_task_type_deletion(self):
        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.guard_task_type_deletion(
                self.task_type_modeling.serialize()
            )
        self.assertEqual(
            str(context.exception),
            "Task type Modeling is used by 2 status automations. Remove it "
            "from them first.",
        )
        status_automations_service.guard_task_type_deletion(
            self.task_type_animation.serialize()
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
        wip_status = task_types_service.get_or_create_task_status(
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


class StatusAutomationTriggerTestCase(ApiDBTestCase):
    """
    How a write sets the trigger: in_conditions, the legacy pair, the
    mirror, and the validation messages.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_retake()
        self.concept_id = str(self.task_type_concept.id)
        self.modeling_id = str(self.task_type_modeling.id)
        self.shaders_id = str(self.task_type.id)
        self.done_id = str(self.task_status_done.id)
        self.wip_id = str(self.task_status_wip.id)
        self.retake_id = str(self.task_status_retake.id)

    def condition(self, task_type_id, *task_status_ids):
        return {
            "task_type_id": task_type_id,
            "task_status_ids": list(task_status_ids),
        }

    def payload(self, **fields):
        data = {
            "entity_type": "asset",
            "out_field_type": "status",
            "out_task_type_id": self.modeling_id,
            "out_task_status_id": self.wip_id,
        }
        data.update(fields)
        return data

    def stored(self, **fields):
        """
        Return a stored automation, created without the API so that it can
        hold what the API refuses.
        """
        data = self.payload()
        data.update(fields)
        return StatusAutomation.create(**data).serialize()

    def test_normalize_legacy_trigger(self):
        data = status_automations_service.normalize_trigger(
            self.payload(
                in_task_type_id=self.concept_id,
                in_task_status_id=self.done_id,
            )
        )
        self.assertEqual(
            data["in_conditions"],
            {
                "operator": "and",
                "conditions": [self.condition(self.concept_id, self.done_id)],
            },
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)
        self.assertEqual(data["in_task_status_id"], self.done_id)

    def test_normalize_simple_trigger_sets_the_mirror(self):
        data = status_automations_service.normalize_trigger(
            self.payload(
                in_conditions={
                    "operator": "or",
                    "conditions": [
                        self.condition(
                            self.concept_id.upper(), self.done_id.upper()
                        )
                    ],
                }
            )
        )
        self.assertEqual(
            data["in_conditions"]["conditions"],
            [self.condition(self.concept_id, self.done_id)],
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)
        self.assertEqual(data["in_task_status_id"], self.done_id)

    def test_normalize_trigger_with_several_conditions(self):
        data = status_automations_service.normalize_trigger(
            self.payload(
                in_task_type_id=self.concept_id,
                in_task_status_id=self.done_id,
                in_conditions={
                    "operator": "and",
                    "conditions": [
                        self.condition(
                            self.concept_id, self.done_id, self.done_id
                        ),
                        self.condition(
                            self.shaders_id, self.done_id, self.retake_id
                        ),
                    ],
                },
            )
        )
        self.assertEqual(
            data["in_conditions"]["conditions"],
            [
                self.condition(self.concept_id, self.done_id),
                self.condition(self.shaders_id, self.done_id, self.retake_id),
            ],
        )
        self.assertIsNone(data["in_task_type_id"])
        self.assertIsNone(data["in_task_status_id"])

    def test_normalize_refuses_invalid_writes(self):
        unknown_id = fields.gen_uuid()
        concept_done = self.condition(self.concept_id, self.done_id)

        def trigger(*conditions, operator="and"):
            return {"operator": operator, "conditions": list(conditions)}

        cases = [
            (
                {"in_conditions": trigger(concept_done, operator="xor")},
                "Trigger operator must be 'and' or 'or'.",
            ),
            (
                {"in_conditions": trigger()},
                "A trigger needs at least one condition.",
            ),
            (
                {
                    "in_conditions": trigger(
                        *[self.condition(fields.gen_uuid(), self.done_id)] * 11
                    )
                },
                "A trigger accepts at most 10 conditions.",
            ),
            (
                {"in_conditions": trigger(trigger(concept_done))},
                "Condition groups are not supported yet.",
            ),
            (
                {"in_conditions": trigger(dict(concept_done, scope="all"))},
                "Unknown field 'scope' in a trigger condition.",
            ),
            (
                {"in_conditions": dict(trigger(concept_done), scope="all")},
                "Unknown field 'scope' in a trigger.",
            ),
            (
                {
                    "in_conditions": trigger(
                        self.condition(unknown_id, self.done_id)
                    )
                },
                f"Task type {unknown_id} does not exist.",
            ),
            (
                {
                    "in_conditions": trigger(
                        self.condition("not-an-id", self.done_id)
                    )
                },
                "Task type not-an-id does not exist.",
            ),
            (
                {
                    "in_conditions": trigger(
                        self.condition(
                            str(self.task_type_layout.id), self.done_id
                        )
                    )
                },
                "Task type Layout is not a task type of assets.",
            ),
            (
                {"in_conditions": trigger(self.condition(self.concept_id))},
                "A condition needs at least one status.",
            ),
            (
                {
                    "in_conditions": trigger(
                        self.condition(self.concept_id, unknown_id)
                    )
                },
                f"Task status {unknown_id} does not exist.",
            ),
            (
                {
                    "in_conditions": trigger(
                        concept_done,
                        self.condition(self.concept_id, self.wip_id),
                        operator="or",
                    )
                },
                "Task type Concept appears in two conditions: merge their "
                "statuses into one.",
            ),
            (
                {
                    "in_conditions": trigger(
                        concept_done,
                        self.condition(self.modeling_id, self.done_id),
                    )
                },
                "The applied task type Modeling cannot be a condition.",
            ),
            (
                {
                    "entity_type": "shot",
                    "out_field_type": "ready_for",
                    "in_conditions": trigger(
                        self.condition(
                            str(self.task_type_animation.id), self.done_id
                        )
                    ),
                },
                "The ready for output applies to assets only.",
            ),
            (
                {
                    "out_field_type": "ready_for",
                    "out_task_type_id": str(self.task_type_layout.id),
                    "out_only_if_task_status_ids": [self.wip_id],
                    "in_conditions": trigger(concept_done),
                },
                "The target status guard applies to status changes only.",
            ),
            (
                {
                    "out_only_if_task_status_ids": [unknown_id],
                    "in_conditions": trigger(concept_done),
                },
                f"Task status {unknown_id} does not exist.",
            ),
            (
                {"in_task_type_id": self.concept_id},
                "in_task_type_id and in_task_status_id go together.",
            ),
            ({}, "A trigger needs at least one condition."),
        ]
        for fields_of_case, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(WrongParameterException) as context:
                    status_automations_service.normalize_trigger(
                        self.payload(**fields_of_case)
                    )
                self.assertEqual(str(context.exception), message)

    def test_normalize_refuses_a_payload_that_is_no_object(self):
        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.normalize_trigger([self.payload()])
        self.assertEqual(str(context.exception), "A JSON object is expected.")

    def test_normalize_stores_the_guard_in_one_form(self):
        """
        Its ids in one form, without duplicates, and an empty guard as null:
        no guard.
        """
        group = {
            "operator": "and",
            "conditions": [self.condition(self.concept_id, self.done_id)],
        }

        data = status_automations_service.normalize_trigger(
            self.payload(
                in_conditions=group,
                out_only_if_task_status_ids=[
                    self.done_id.upper(),
                    self.retake_id,
                    self.done_id,
                ],
            )
        )
        self.assertEqual(
            data["out_only_if_task_status_ids"],
            [self.done_id, self.retake_id],
        )

        data = status_automations_service.normalize_trigger(
            self.payload(in_conditions=group, out_only_if_task_status_ids=[])
        )
        self.assertIsNone(data["out_only_if_task_status_ids"])

    def test_update_round_trip_keeps_the_conditions(self):
        """
        Clients send back what they read: the conditions, statuses in
        another order, and the stale null mirror.
        """
        group = {
            "operator": "and",
            "conditions": [
                self.condition(self.concept_id, self.done_id, self.retake_id),
                self.condition(self.shaders_id, self.done_id),
            ],
        }
        instance = self.stored(in_conditions=group)
        sent = {
            "operator": "and",
            "conditions": [
                self.condition(self.concept_id, self.retake_id, self.done_id),
                self.condition(self.shaders_id, self.done_id),
            ],
        }

        data = status_automations_service.normalize_trigger(
            {
                "in_conditions": sent,
                "in_task_type_id": None,
                "in_task_status_id": None,
                "archived": True,
            },
            instance,
        )

        self.assertEqual(data["in_conditions"], group)
        self.assertIsNone(data["in_task_type_id"])
        self.assertIsNone(data["in_task_status_id"])

    def test_update_refuses_a_legacy_write_on_several_conditions(self):
        instance = self.stored(
            in_conditions={
                "operator": "or",
                "conditions": [
                    self.condition(self.concept_id, self.done_id),
                    self.condition(self.shaders_id, self.done_id),
                ],
            }
        )
        for legacy in (
            {"in_task_type_id": self.concept_id},
            {
                "in_task_type_id": self.concept_id,
                "in_task_status_id": self.done_id,
            },
        ):
            with self.subTest(legacy=legacy):
                with self.assertRaises(WrongParameterException) as context:
                    status_automations_service.normalize_trigger(
                        legacy, instance
                    )
                self.assertEqual(
                    str(context.exception),
                    "This automation has several trigger conditions: update "
                    "it through in_conditions.",
                )

    def test_update_completes_a_half_legacy_pair(self):
        instance = self.stored(
            in_task_type_id=self.concept_id, in_task_status_id=self.done_id
        )

        data = status_automations_service.normalize_trigger(
            {"in_task_status_id": self.retake_id}, instance
        )

        self.assertEqual(
            data["in_conditions"]["conditions"],
            [self.condition(self.concept_id, self.retake_id)],
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)
        self.assertEqual(data["in_task_status_id"], self.retake_id)

    def test_update_of_unchanged_fields_skips_the_validation(self):
        """
        A stored row breaking a rule stays editable: archiving it sends the
        whole form back, with an empty guard where null is stored.
        """
        group = {
            "operator": "and",
            "conditions": [
                self.condition(str(self.task_type_layout.id), self.done_id)
            ],
        }
        instance = self.stored(in_conditions=group)

        data = status_automations_service.normalize_trigger(
            self.payload(
                in_conditions=group,
                out_only_if_task_status_ids=[],
                archived=True,
            ),
            instance,
        )

        self.assertEqual(data["in_conditions"], group)
        self.assertIsNone(data["out_only_if_task_status_ids"])

    def test_update_applies_a_legacy_write_next_to_an_unchanged_trigger(
        self,
    ):
        """
        A script that reads a row and sends it back with another
        in_task_status_id sets that status: the unchanged in_conditions of
        the row does not hide it.
        """
        instance = self.stored(
            in_conditions={
                "operator": "and",
                "conditions": [self.condition(self.concept_id, self.done_id)],
            },
            in_task_type_id=self.concept_id,
            in_task_status_id=self.done_id,
        )

        data = status_automations_service.normalize_trigger(
            dict(instance, in_task_status_id=self.retake_id), instance
        )

        self.assertEqual(
            data["in_conditions"]["conditions"],
            [self.condition(self.concept_id, self.retake_id)],
        )
        self.assertEqual(data["in_task_status_id"], self.retake_id)

    def test_update_ignores_a_null_legacy_pair_next_to_in_conditions(self):
        """
        A client writing in_conditions may send the deprecated pair as null
        next to it: the trigger follows in_conditions, changed or not, and
        the stored pair stays, even next to a malformed trigger. Next to the
        stored trigger, a single null changing that pair is refused, as
        without in_conditions.
        """
        group = {
            "operator": "and",
            "conditions": [self.condition(self.concept_id, self.done_id)],
        }
        retake_group = {
            "operator": "and",
            "conditions": [self.condition(self.concept_id, self.retake_id)],
        }
        instance = self.stored(
            in_conditions=group,
            in_task_type_id=self.concept_id,
            in_task_status_id=self.done_id,
        )
        null_pair = {"in_task_type_id": None, "in_task_status_id": None}
        for label, sent in (("unchanged", group), ("changed", retake_group)):
            with self.subTest(case=label):
                data = status_automations_service.normalize_trigger(
                    dict(null_pair, in_conditions=sent), instance
                )

                self.assertEqual(
                    data["in_conditions"]["conditions"], sent["conditions"]
                )
                self.assertEqual(data["in_task_type_id"], self.concept_id)
                self.assertEqual(
                    data["in_task_status_id"],
                    sent["conditions"][0]["task_status_ids"][0],
                )

        malformed = {"operator": "xor", "conditions": "broken"}
        data = status_automations_service.normalize_trigger(
            dict(null_pair, in_conditions=malformed, archived=True),
            self.stored(
                in_conditions=malformed,
                in_task_type_id=self.concept_id,
                in_task_status_id=self.done_id,
            ),
        )
        self.assertNotIn("in_task_type_id", data)
        self.assertNotIn("in_task_status_id", data)

        for legacy in (
            {"in_task_status_id": None},
            {"in_task_type_id": None, "in_task_status_id": self.retake_id},
        ):
            with self.subTest(legacy=legacy):
                with self.assertRaises(WrongParameterException) as context:
                    status_automations_service.normalize_trigger(
                        dict(legacy, in_conditions=group), instance
                    )
                self.assertEqual(
                    str(context.exception),
                    "in_task_type_id and in_task_status_id go together.",
                )

    def test_a_single_null_next_to_a_new_trigger_is_not_read(self):
        """
        Like any legacy value: in_conditions gives the trigger when it
        changes it, and the mirror follows.
        """
        group = {
            "operator": "and",
            "conditions": [self.condition(self.concept_id, self.retake_id)],
        }
        for label, instance in (
            ("creation", None),
            (
                "update",
                self.stored(
                    in_task_type_id=self.concept_id,
                    in_task_status_id=self.done_id,
                ),
            ),
        ):
            with self.subTest(case=label):
                data = status_automations_service.normalize_trigger(
                    self.payload(in_conditions=group, in_task_status_id=None),
                    instance,
                )

                self.assertEqual(data["in_task_type_id"], self.concept_id)
                self.assertEqual(data["in_task_status_id"], self.retake_id)

    def test_update_cannot_clear_the_trigger(self):
        """
        A null legacy pair does not clear the trigger: archiving the
        automation stops it.
        """
        instance = self.stored(
            in_task_type_id=self.concept_id, in_task_status_id=self.done_id
        )

        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.normalize_trigger(
                {"in_task_type_id": None, "in_task_status_id": None}, instance
            )
        self.assertEqual(
            str(context.exception), "A trigger needs at least one condition."
        )

    def test_ids_compare_in_any_case(self):
        """
        An id in capitals names the same row: it does not slip the applied
        task type into the conditions, nor make an untouched row look
        changed.
        """
        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.normalize_trigger(
                self.payload(
                    in_conditions={
                        "operator": "and",
                        "conditions": [
                            self.condition(self.modeling_id, self.done_id)
                        ],
                    },
                    out_task_type_id=self.modeling_id.upper(),
                )
            )
        self.assertEqual(
            str(context.exception),
            "The applied task type Modeling cannot be a condition.",
        )

        layout_id = str(self.task_type_layout.id)
        instance = self.stored(
            in_conditions={
                "operator": "and",
                "conditions": [self.condition(layout_id, self.done_id)],
            },
            in_task_type_id=layout_id,
            in_task_status_id=self.done_id,
        )
        data = status_automations_service.normalize_trigger(
            self.payload(
                in_task_type_id=layout_id.upper(),
                in_task_status_id=self.done_id.upper(),
                out_task_type_id=self.modeling_id.upper(),
                archived=True,
            ),
            instance,
        )
        self.assertEqual(data["in_task_type_id"], layout_id)

    def test_entity_types_compare_in_any_case(self):
        """
        Older clients wrote capitalized entity types: "Asset" is "asset".
        """
        layout_group = {
            "operator": "and",
            "conditions": [
                self.condition(str(self.task_type_layout.id), self.done_id)
            ],
        }
        instance = self.stored(entity_type="Asset", in_conditions=layout_group)
        status_automations_service.normalize_trigger(
            self.payload(in_conditions=layout_group, archived=True), instance
        )

        data = status_automations_service.normalize_trigger(
            self.payload(
                entity_type="Asset",
                out_field_type="ready_for",
                out_task_type_id=str(self.task_type_layout.id),
                out_task_status_id=None,
                in_conditions={
                    "operator": "and",
                    "conditions": [
                        self.condition(self.concept_id, self.done_id)
                    ],
                },
            )
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)

    def test_an_asset_type_row_takes_the_asset_task_types(self):
        """
        Old rows can name an asset type ("props") instead of "asset": their
        trigger and output take the asset task types.
        """
        self.generate_fixture_asset_type()
        concept_done = {
            "operator": "and",
            "conditions": [self.condition(self.concept_id, self.done_id)],
        }

        data = status_automations_service.normalize_trigger(
            self.payload(entity_type="props", in_conditions=concept_done)
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)

        data = status_automations_service.normalize_trigger(
            self.payload(
                entity_type="props",
                out_field_type="ready_for",
                out_task_type_id=str(self.task_type_layout.id),
                out_task_status_id=None,
                in_conditions=concept_done,
            )
        )
        self.assertEqual(data["in_task_type_id"], self.concept_id)

        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.normalize_trigger(
                self.payload(
                    entity_type="props",
                    in_conditions={
                        "operator": "and",
                        "conditions": [
                            self.condition(
                                str(self.task_type_layout.id), self.done_id
                            )
                        ],
                    },
                )
            )
        self.assertEqual(
            str(context.exception),
            "Task type Layout is not a task type of assets.",
        )

    def test_a_task_type_without_entity_is_an_asset_one(self):
        """
        A task type older than for_entity reads null there, which Zou takes
        as "Asset", the default.
        """
        grooming = TaskType.create(
            name="Grooming", short_name="groom", color="#FFFFFF"
        )
        grooming.update({"for_entity": None})
        self.assertIsNone(TaskType.get(grooming.id).for_entity)
        grooming_id = str(grooming.id)

        data = status_automations_service.normalize_trigger(
            self.payload(
                in_task_type_id=grooming_id, in_task_status_id=self.done_id
            )
        )
        self.assertEqual(data["in_task_type_id"], grooming_id)

        with self.assertRaises(WrongParameterException) as context:
            status_automations_service.normalize_trigger(
                self.payload(
                    entity_type="shot",
                    in_task_type_id=grooming_id,
                    in_task_status_id=self.done_id,
                    out_task_type_id=str(self.task_type_animation.id),
                )
            )
        self.assertEqual(
            str(context.exception),
            "Task type Grooming is not a task type of shots.",
        )

    def test_update_keeps_a_malformed_trigger_sent_back(self):
        """
        A script that reads a row and sends it back whole is not refused
        for a malformed trigger it leaves as it is.
        """
        group = {"operator": "xor", "conditions": "broken"}
        instance = self.stored(in_conditions=group)

        data = status_automations_service.normalize_trigger(
            dict(instance, archived=True), instance
        )

        self.assertEqual(data["in_conditions"], group)
        self.assertNotIn("in_task_type_id", data)

    def test_get_trigger(self):
        legacy = {
            "id": str(fields.gen_uuid()),
            "in_conditions": None,
            "in_task_type_id": self.concept_id,
            "in_task_status_id": self.done_id,
        }
        self.assertEqual(
            status_automations_service.get_trigger(legacy),
            {
                "operator": "and",
                "conditions": [self.condition(self.concept_id, self.done_id)],
            },
        )
        for automation in (
            dict(legacy, in_conditions="all of them"),
            dict(legacy, in_conditions={"operator": "and", "conditions": []}),
            dict(legacy, in_task_status_id=None),
            {"id": str(fields.gen_uuid()), "in_conditions": None},
        ):
            with self.subTest(automation=automation):
                with self.assertLogs(
                    current_app.logger, level="WARNING"
                ) as logs:
                    self.assertIsNone(
                        status_automations_service.get_trigger(automation)
                    )
                self.assertIn(automation["id"], logs.output[0])

    def test_create_from_import_derives_the_trigger(self):
        """
        A sync from an instance older than the trigger groups sends the
        legacy columns only.
        """
        automation_id = fields.gen_uuid()
        StatusAutomation.create_from_import(
            self.payload(
                id=automation_id,
                in_task_type_id=self.concept_id,
                in_task_status_id=self.done_id,
            )
        )
        self.assertEqual(
            StatusAutomation.get(automation_id).in_conditions,
            {
                "operator": "and",
                "conditions": [self.condition(self.concept_id, self.done_id)],
            },
        )

    def test_usage_lookups_read_the_conditions_and_the_guard(self):
        automation_id = self.stored(
            in_conditions={
                "operator": "and",
                "conditions": [
                    self.condition(
                        self.concept_id, self.done_id, self.retake_id
                    )
                ],
            },
            out_only_if_task_status_ids=[str(self.task_status.id)],
        )["id"]
        service = status_automations_service

        self.assertIn(
            automation_id,
            [
                automation["id"]
                for automation in service.get_automations_using_task_type(
                    self.concept_id
                )
            ],
        )
        for task_status_id in (self.retake_id, str(self.task_status.id)):
            self.assertIn(
                automation_id,
                [
                    automation["id"]
                    for automation in (
                        service.get_automations_using_task_status(
                            task_status_id
                        )
                    )
                ],
            )

    def test_usage_lookups_read_past_an_id_that_is_no_string(self):
        """
        One row holding a list or an object as an id, which only a direct
        write stores, must not fail every deletion of a task type or status.
        """
        self.stored(
            in_conditions={
                "operator": "and",
                "conditions": [
                    {
                        "task_type_id": [self.concept_id],
                        "task_status_ids": [{"id": self.done_id}],
                    }
                ],
            },
            out_only_if_task_status_ids=[[self.done_id]],
        )
        service = status_automations_service

        self.assertEqual(
            service.get_automations_using_task_type(self.shaders_id), []
        )
        self.assertEqual(
            service.get_automations_using_task_status(self.retake_id), []
        )


class StatusAutomationRunnerTestCase(ApiDBTestCase):
    """
    An automation fires on the status change that turns its trigger from
    false to true.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.todo = TaskStatus.create(
            name="Todo", short_name="todo", color="#FFFFFF", is_default=True
        )
        self.ready = TaskStatus.create(
            name="Ready", short_name="ready", color="#FFFFFF"
        )
        self.wip = TaskStatus.create(
            name="WIP", short_name="wip", color="#FFFFFF", is_wip=True
        )
        self.done = TaskStatus.create(
            name="Done", short_name="done", color="#FFFFFF", is_done=True
        )
        self.na = TaskStatus.create(
            name="NA", short_name="na", color="#FFFFFF", is_done=True
        )
        self.retake = TaskStatus.create(
            name="Retake", short_name="rtk", color="#FFFFFF", is_retake=True
        )

    def a_task_type(self, name, for_entity="Shot", priority=None):
        task_type = TaskType.create(
            name=name,
            short_name=name.lower()[:8],
            color="#FFFFFF",
            for_entity=for_entity,
            department_id=self.department.id,
        )
        if priority is not None:
            ProjectTaskTypeLink.create(
                project_id=self.project.id,
                task_type_id=task_type.id,
                priority=priority,
            )
        return task_type

    def a_task(self, entity, task_type, name=None, status=None, **extra):
        return Task.create(
            name=name or task_type.name,
            project_id=self.project.id,
            task_type_id=task_type.id,
            task_status_id=(status or self.todo).id,
            entity_id=entity.id,
            assigner_id=self.assigner.id,
            **extra,
        )

    def an_automation(
        self,
        entity_type,
        operator,
        conditions,
        out_task_type,
        out_task_status=None,
        out_field_type="status",
        **extra,
    ):
        automation = StatusAutomation.create(
            **extra,
            entity_type=entity_type,
            in_conditions={
                "operator": operator,
                "conditions": [
                    {
                        "task_type_id": str(task_type.id),
                        "task_status_ids": [
                            str(task_status.id) for task_status in statuses
                        ],
                    }
                    for task_type, statuses in conditions
                ],
            },
            out_field_type=out_field_type,
            out_task_type_id=out_task_type.id,
            out_task_status_id=(
                out_task_status.id if out_task_status else None
            ),
        )
        projects_service.add_status_automation_setting(
            self.project.id, automation.id
        )
        return automation

    def automations_in_order(self, *automations):
        """
        Date the automations in given order, a minute apart: the runner
        applies them in the order they were created, and a test whose point
        is a chain or a failure needs the automation that starts it to come
        first, whatever the clock.
        """
        start = datetime.datetime(2026, 1, 1)
        for index, automation in enumerate(automations):
            automation.update(
                {"created_at": start + datetime.timedelta(minutes=index)}
            )

    def comment(self, task, task_status, text="Test", created_at=""):
        return comments_service.create_comment(
            str(self.person.id),
            str(task.id),
            str(task_status.id),
            text,
            [],
            {},
            created_at,
        )

    def assert_status(self, task, task_status):
        self.assertEqual(
            str(Task.get(task.id).task_status_id), str(task_status.id)
        )

    def comment_texts(self, task):
        return [
            comment.text
            for comment in Comment.query.filter_by(object_id=task.id)
            .order_by(Comment.created_at)
            .all()
        ]

    def test_and_fires_when_the_last_condition_is_met(self):
        lighting = self.a_task_type("Lighting")
        fx = self.a_task_type("FX")
        compositing = self.a_task_type("Compositing")
        lighting_task = self.a_task(self.shot, lighting)
        fx_task = self.a_task(self.shot, fx)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "and",
            [(lighting, [self.done]), (fx, [self.done])],
            compositing,
            self.ready,
        )

        self.comment(fx_task, self.done)
        self.assert_status(compositing_task, self.todo)
        self.comment(lighting_task, self.done)

        self.assert_status(compositing_task, self.ready)
        self.assertEqual(
            self.comment_texts(compositing_task),
            ["Change triggered by Lighting set to Done and FX set to Done"],
        )

    def test_a_comment_without_status_change_does_not_fire(self):
        """
        A plain note on a task already at a trigger status used to post the
        output status again, over the work in progress.
        """
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        layout_task = self.a_task(self.shot, layout)
        animation_task = self.a_task(self.shot, animation)
        self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )
        self.comment(layout_task, self.done)
        self.comment(animation_task, self.wip)

        self.comment(layout_task, self.done, "Just a note")

        self.assert_status(animation_task, self.wip)
        self.assertEqual(len(self.comment_texts(animation_task)), 2)

    def test_an_archived_automation_does_not_fire(self):
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        self.an_automation(
            "shot",
            "and",
            [(animation, [self.done])],
            lighting,
            self.ready,
            archived=True,
        )

        self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.todo)

    def test_a_missing_task_type_is_ignored(self):
        lighting = self.a_task_type("Lighting")
        fx = self.a_task_type("FX")
        compositing = self.a_task_type("Compositing")
        lighting_task = self.a_task(self.shot, lighting)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "and",
            [(lighting, [self.done]), (fx, [self.done])],
            compositing,
            self.ready,
        )

        self.comment(lighting_task, self.done)

        self.assert_status(compositing_task, self.ready)

    def test_or_does_not_fire_on_a_second_condition(self):
        concept = self.a_task_type("Concept", "Asset")
        sculpt = self.a_task_type("Sculpt", "Asset")
        modeling = self.a_task_type("Modeling", "Asset")
        concept_task = self.a_task(self.asset, concept)
        sculpt_task = self.a_task(self.asset, sculpt)
        modeling_task = self.a_task(self.asset, modeling)
        self.an_automation(
            "asset",
            "or",
            [(concept, [self.done]), (sculpt, [self.done])],
            modeling,
            self.ready,
        )

        self.comment(concept_task, self.done)
        self.assert_status(modeling_task, self.ready)
        self.assertEqual(
            self.comment_texts(modeling_task),
            ["Change triggered by Concept set to Done"],
        )
        self.comment(modeling_task, self.wip)
        self.comment(sculpt_task, self.done)

        self.assert_status(modeling_task, self.wip)

    def test_every_task_of_a_condition_type_has_to_match(self):
        lighting = self.a_task_type("Lighting")
        fx = self.a_task_type("FX")
        compositing = self.a_task_type("Compositing")
        self.a_task(self.shot, lighting, status=self.done)
        main_fx_task = self.a_task(self.shot, fx, "FX main")
        extra_fx_task = self.a_task(self.shot, fx, "FX extra")
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "and",
            [(lighting, [self.done]), (fx, [self.done, self.na])],
            compositing,
            self.ready,
        )

        self.comment(main_fx_task, self.na)
        self.assert_status(compositing_task, self.todo)
        self.comment(extra_fx_task, self.done)

        self.assert_status(compositing_task, self.ready)

    def test_a_downstream_condition_never_fires_under_and(self):
        lighting = self.a_task_type("Lighting", priority=1)
        compositing = self.a_task_type("Compositing", priority=2)
        fx = self.a_task_type("FX", priority=3)
        lighting_task = self.a_task(self.shot, lighting)
        fx_task = self.a_task(self.shot, fx)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "and",
            [(lighting, [self.done]), (fx, [self.done])],
            compositing,
            self.ready,
        )

        self.comment(lighting_task, self.done)
        self.comment(fx_task, self.done)
        self.assert_status(compositing_task, self.todo)
        self.comment(lighting_task, self.wip)
        self.comment(lighting_task, self.done)

        self.assert_status(compositing_task, self.ready)

    def test_a_downstream_condition_is_left_out_under_or(self):
        """
        Once met, a downstream condition would keep the trigger met and
        block every later change.
        """
        lighting = self.a_task_type("Lighting", priority=1)
        compositing = self.a_task_type("Compositing", priority=2)
        fx = self.a_task_type("FX", priority=3)
        lighting_task = self.a_task(self.shot, lighting)
        fx_task = self.a_task(self.shot, fx)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "or",
            [(lighting, [self.done]), (fx, [self.done])],
            compositing,
            self.ready,
        )

        self.comment(fx_task, self.done)
        self.assert_status(compositing_task, self.todo)
        self.comment(lighting_task, self.done)

        self.assert_status(compositing_task, self.ready)

    def test_a_ready_for_fires_on_a_downstream_condition(self):
        """
        Only a status output can start a cycle: a ready for reads every
        condition the same, whatever its place in the production.
        """
        modeling = self.a_task_type("Modeling", "Asset", priority=2)
        layout = self.a_task_type("Layout")
        modeling_task = self.a_task(self.asset, modeling)
        self.an_automation(
            "asset",
            "and",
            [(modeling, [self.done])],
            layout,
            out_field_type="ready_for",
        )

        self.comment(modeling_task, self.done)

        self.assertEqual(
            str(Entity.get(self.asset.id).ready_for), str(layout.id)
        )

    def test_equal_priorities_fire(self):
        layout = self.a_task_type("Layout", priority=2)
        animation = self.a_task_type("Animation", priority=2)
        layout_task = self.a_task(self.shot, layout)
        animation_task = self.a_task(self.shot, animation)
        self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )

        self.comment(layout_task, self.done)

        self.assert_status(animation_task, self.ready)

    def test_revision_source(self):
        lighting_id = str(fields.gen_uuid())
        fx_id = str(fields.gen_uuid())
        conditions = [
            {"task_type_id": lighting_id, "is_known": True},
            {"task_type_id": fx_id, "is_known": True},
        ]
        tasks_by_type = {
            lighting_id: [{"id": "lighting-1", "task_status_id": ""}],
            fx_id: [{"id": "fx-1", "task_status_id": ""}],
        }
        fx_task = {"id": "fx-1", "task_type_id": fx_id}
        get_source = comments_service._get_revision_source_task_id

        self.assertEqual(
            get_source(
                {"operator": "and"}, conditions, fx_task, tasks_by_type
            ),
            "lighting-1",
        )
        self.assertEqual(
            get_source(
                {"operator": "and"},
                conditions,
                fx_task,
                {fx_id: tasks_by_type[fx_id]},
            ),
            "fx-1",
        )
        self.assertEqual(
            get_source({"operator": "or"}, conditions, fx_task, tasks_by_type),
            "fx-1",
        )

    def test_a_single_condition_keeps_its_comment_text(self):
        concept = self.a_task_type("Concept", "Asset")
        modeling = self.a_task_type("Modeling", "Asset")
        concept_task = self.a_task(self.asset, concept)
        modeling_task = self.a_task(self.asset, modeling)
        self.an_automation(
            "asset", "and", [(concept, [self.done])], modeling, self.wip
        )

        self.comment(concept_task, self.done)
        self.comment(concept_task, self.done, "Same status again")

        self.assertEqual(
            self.comment_texts(modeling_task),
            ["Change triggered by Concept set to Done"],
        )

    def test_a_back_dated_comment_fires_on_a_replayed_change_only(self):
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        layout_task = self.a_task(self.shot, layout)
        animation_task = self.a_task(self.shot, animation)
        self.comment(layout_task, self.wip)
        self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )

        self.comment(
            layout_task, self.done, "Old", created_at="2020-01-01 10:00:00"
        )
        self.assert_status(layout_task, self.wip)
        self.assert_status(animation_task, self.todo)

        # Changed without a comment: the replay goes back to the status of
        # the last comment.
        tasks_service.update_task(
            str(layout_task.id), {"task_status_id": str(self.done.id)}
        )
        self.an_automation(
            "shot", "and", [(layout, [self.wip])], animation, self.retake
        )
        self.comment(
            layout_task, self.na, "Older", created_at="2020-01-01 09:00:00"
        )
        self.assert_status(layout_task, self.wip)
        self.assert_status(animation_task, self.retake)

    def test_unknown_ids(self):
        lighting = self.a_task_type("Lighting")
        compositing = self.a_task_type("Compositing")
        lighting_task = self.a_task(self.shot, lighting)
        compositing_task = self.a_task(self.shot, compositing)
        automation = self.an_automation(
            "shot", "and", [(lighting, [self.done])], compositing, self.ready
        )
        condition = {
            "task_type_id": str(lighting.id),
            "task_status_ids": [str(self.done.id), str(fields.gen_uuid())],
        }
        unknown_condition = {
            "task_type_id": str(fields.gen_uuid()),
            "task_status_ids": [str(self.done.id)],
        }
        automation.update(
            {
                "in_conditions": {
                    "operator": "and",
                    "conditions": [condition, unknown_condition],
                }
            }
        )

        self.comment(lighting_task, self.done)
        self.assert_status(compositing_task, self.todo)

        automation.update(
            {"in_conditions": {"operator": "and", "conditions": [condition]}}
        )
        self.comment(lighting_task, self.wip)
        self.comment(lighting_task, self.done)
        self.assert_status(compositing_task, self.ready)

    def test_a_malformed_trigger_does_not_fail_the_comment(self):
        lighting = self.a_task_type("Lighting")
        compositing = self.a_task_type("Compositing")
        review = self.a_task_type("Review")
        lighting_task = self.a_task(self.shot, lighting)
        compositing_task = self.a_task(self.shot, compositing)
        review_task = self.a_task(self.shot, review)
        automation = self.an_automation(
            "shot", "and", [(lighting, [self.done])], compositing, self.ready
        )
        automation.update(
            {"in_conditions": {"operator": "and", "conditions": "broken"}}
        )
        healthy = self.an_automation(
            "shot", "and", [(lighting, [self.done])], review, self.ready
        )

        self.automations_in_order(automation, healthy)
        with self.assertLogs(current_app.logger, level="WARNING") as logs:
            self.comment(lighting_task, self.done)

        self.assert_status(lighting_task, self.done)
        self.assert_status(compositing_task, self.todo)
        self.assert_status(review_task, self.ready)
        self.assertIn(
            f"Status automation {automation.id} has a malformed trigger",
            "\n".join(logs.output),
        )

    def test_a_failing_automation_does_not_stop_the_others(self):
        """
        An automation that fails in the database as it applies its change
        is logged, and what it had not saved yet is rolled back: the comment
        stays, and the next automation still reaches the database to apply
        its own.
        """
        lighting = self.a_task_type("Lighting")
        compositing = self.a_task_type("Compositing")
        review = self.a_task_type("Review")
        lighting_task = self.a_task(self.shot, lighting)
        self.a_task(self.shot, compositing)
        review_task = self.a_task(self.shot, review)
        broken = self.an_automation(
            "shot", "and", [(lighting, [self.done])], compositing, self.ready
        )
        broken.update({"import_last_revision": True})
        healthy = self.an_automation(
            "shot", "and", [(lighting, [self.done])], review, self.ready
        )

        def fail_in_the_database(*args):
            db.session.execute(text("SELECT 1 / 0"))

        self.automations_in_order(broken, healthy)
        self.spare_fixtures_from_rollbacks()
        with mock.patch.object(
            comments_service,
            "_import_last_revision",
            side_effect=fail_in_the_database,
        ), self.assertLogs(current_app.logger, level="ERROR") as logs:
            comment = self.comment(lighting_task, self.done)

        self.assertEqual(comment["task_status_id"], str(self.done.id))
        self.assertEqual(len(self.comment_texts(lighting_task)), 1)
        self.assert_status(lighting_task, self.done)
        self.assert_status(review_task, self.ready)
        self.assertIn(
            f"Status automation {broken.id} failed on task {lighting_task.id}",
            "\n".join(logs.output),
        )

    def test_a_hashtag_copy_does_not_fire(self):
        lighting = self.a_task_type("Lighting")
        fx = self.a_task_type("FX")
        compositing = self.a_task_type("Compositing")
        lighting_task = self.a_task(self.shot, lighting)
        fx_task = self.a_task(self.shot, fx, status=self.done)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot", "or", [(fx, [self.done])], compositing, self.ready
        )

        self.comment(lighting_task, self.wip, "#fx please check")

        self.assertEqual(len(self.comment_texts(fx_task)), 1)
        self.assert_status(compositing_task, self.todo)

    def test_a_retake_cap_on_the_target_skips_the_output(self):
        self.project.update({"max_retakes": 1})
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        layout_task = self.a_task(self.shot, layout)
        animation_task = self.a_task(self.shot, animation, retake_count=1)
        self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.retake
        )

        self.comment(layout_task, self.done)

        self.assert_status(layout_task, self.done)
        self.assert_status(animation_task, self.todo)

    def test_ready_for_with_several_conditions(self):
        modeling = self.a_task_type("Modeling", "Asset")
        rigging = self.a_task_type("Rigging", "Asset")
        layout = self.a_task_type("Layout")
        modeling_task = self.a_task(self.asset, modeling)
        rigging_task = self.a_task(self.asset, rigging)
        self.an_automation(
            "asset",
            "and",
            [(modeling, [self.done]), (rigging, [self.done])],
            layout,
            out_field_type="ready_for",
        )

        self.comment(modeling_task, self.done)
        self.assertIsNone(Entity.get(self.asset.id).ready_for)
        self.comment(rigging_task, self.done)

        self.assertEqual(
            str(Entity.get(self.asset.id).ready_for), str(layout.id)
        )

    def test_a_cycle_fires_each_automation_once(self):
        """
        Between two task types of equal priority, statuses can alternate
        forever: each automation fires once per entity for one action.
        """
        first = self.a_task_type("First")
        second = self.a_task_type("Second")
        first_task = self.a_task(self.shot, first)
        second_task = self.a_task(self.shot, second)
        self.an_automation(
            "shot", "and", [(first, [self.done])], second, self.ready
        )
        self.an_automation(
            "shot", "and", [(second, [self.ready])], first, self.wip
        )
        self.an_automation(
            "shot", "and", [(first, [self.wip])], second, self.todo
        )
        self.an_automation(
            "shot", "and", [(second, [self.todo])], first, self.done
        )

        with self.assertLogs(current_app.logger, level="WARNING") as logs:
            self.comment(first_task, self.done)

        self.assert_status(first_task, self.done)
        self.assert_status(second_task, self.todo)
        self.assertEqual(len(self.comment_texts(first_task)), 3)
        self.assertEqual(len(self.comment_texts(second_task)), 2)
        self.assertTrue(
            any("cycle stopped" in line for line in logs.output), logs.output
        )

    def test_a_cycle_sets_the_ready_for_once(self):
        """
        A ready for fires like a status change: once per entity for one
        action, however often a cycle meets its trigger again.
        """
        first = self.a_task_type("First", "Asset")
        second = self.a_task_type("Second", "Asset")
        layout = self.a_task_type("Layout")
        first_task = self.a_task(self.asset, first)
        self.a_task(self.asset, second)
        self.an_automation(
            "asset", "and", [(first, [self.done])], second, self.ready
        )
        self.an_automation(
            "asset", "and", [(second, [self.ready])], first, self.wip
        )
        self.an_automation(
            "asset", "and", [(first, [self.wip])], second, self.todo
        )
        self.an_automation(
            "asset", "and", [(second, [self.todo])], first, self.done
        )
        self.an_automation(
            "asset",
            "and",
            [(first, [self.done])],
            layout,
            out_field_type="ready_for",
        )

        with mock.patch.object(
            assets_service, "update_asset", wraps=assets_service.update_asset
        ) as update_asset:
            self.comment(first_task, self.done)

        self.assertEqual(update_asset.call_count, 1)

    def test_a_chain_stops_after_ten_automation_comments(self):
        task_types = [self.a_task_type(f"Step {index}") for index in range(12)]
        tasks = [self.a_task(self.shot, task_type) for task_type in task_types]
        for source, target in zip(task_types, task_types[1:]):
            self.an_automation(
                "shot", "and", [(source, [self.done])], target, self.done
            )

        with self.assertLogs(current_app.logger, level="WARNING") as logs:
            self.comment(tasks[0], self.done)

        self.assert_status(tasks[10], self.done)
        self.assert_status(tasks[11], self.todo)
        self.assertTrue(
            any("chained automation comments" in line for line in logs.output),
            logs.output,
        )

    def test_the_chain_cap_warns_only_about_a_fire_it_stops(self):
        task_types = [self.a_task_type(f"Step {index}") for index in range(11)]
        tasks = [self.a_task(self.shot, task_type) for task_type in task_types]
        for source, target in zip(task_types, task_types[1:]):
            self.an_automation(
                "shot", "and", [(source, [self.done])], target, self.done
            )
        # The tenth automation comment, on the last step, meets a trigger
        # that does not fire.
        other = self.a_task_type("Other")
        self.a_task(self.shot, other)
        self.an_automation(
            "shot", "and", [(task_types[10], [self.wip])], other, self.done
        )

        with self.assertNoLogs(current_app.logger, level="WARNING"):
            self.comment(tasks[0], self.done)

        self.assert_status(tasks[10], self.done)

    def test_the_target_guard_keeps_the_work_in_progress(self):
        """
        Without a guard, a retake of the input followed by done again sets
        the target back to the output status, over the work in progress.
        """
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        automation = self.an_automation(
            "shot", "and", [(animation, [self.done])], lighting, self.ready
        )
        automation.update(
            {
                "out_only_if_task_status_ids": [
                    str(self.todo.id),
                    str(self.ready.id),
                ]
            }
        )

        self.comment(animation_task, self.done)
        self.assert_status(lighting_task, self.ready)
        self.comment(lighting_task, self.wip)
        self.comment(animation_task, self.retake)
        self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.wip)
        self.assertEqual(len(self.comment_texts(lighting_task)), 2)

    def test_without_a_target_guard_the_target_is_overwritten(self):
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting, status=self.wip)
        self.an_automation(
            "shot", "and", [(animation, [self.done])], lighting, self.ready
        )

        self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.ready)

    def test_an_empty_target_guard_is_no_guard(self):
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting, status=self.wip)
        automation = self.an_automation(
            "shot", "and", [(animation, [self.done])], lighting, self.ready
        )
        automation.update({"out_only_if_task_status_ids": []})

        self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.ready)

    def test_a_malformed_target_guard_reads_as_none(self):
        """
        A guard that is not a list, which only a direct write stores, reads
        as none, as in Kitsu and on a write: the change applies, with a
        warning.
        """
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting, status=self.wip)
        automation = self.an_automation(
            "shot", "and", [(animation, [self.done])], lighting, self.ready
        )
        automation.update({"out_only_if_task_status_ids": str(self.todo.id)})

        with self.assertLogs(current_app.logger, level="WARNING") as logs:
            self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.ready)
        self.assertIn(
            f"Status automation {automation.id} has a malformed target "
            "guard, read as none",
            "\n".join(logs.output),
        )

    def test_an_or_trigger_is_decided_before_the_cascade(self):
        """
        Every automation of a comment is decided on the tasks as the comment
        leaves them: what an automation listed first changes does not make
        the trigger look met before.
        """
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        layout_task = self.a_task(self.shot, layout, status=self.wip)
        self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        cascade = self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )
        either = self.an_automation(
            "shot",
            "or",
            [(layout, [self.done]), (animation, [self.ready])],
            lighting,
            self.ready,
        )

        self.automations_in_order(cascade, either)
        self.comment(layout_task, self.done)

        self.assert_status(lighting_task, self.ready)
        self.assertEqual(
            self.comment_texts(lighting_task),
            ["Change triggered by Layout set to Done"],
        )

    def test_an_or_trigger_met_before_does_not_fire_after_a_cascade(self):
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        layout_task = self.a_task(self.shot, layout, status=self.wip)
        self.a_task(self.shot, animation, status=self.ready)
        lighting_task = self.a_task(self.shot, lighting, status=self.wip)
        cascade = self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.wip
        )
        either = self.an_automation(
            "shot",
            "or",
            [(layout, [self.done]), (animation, [self.ready])],
            lighting,
            self.ready,
        )

        self.automations_in_order(cascade, either)
        self.comment(layout_task, self.done)

        self.assert_status(lighting_task, self.wip)

    def test_a_later_change_of_the_commented_task_does_not_cancel_a_fire(
        self,
    ):
        """
        As before the trigger groups, each automation reads the status the
        comment set, even once a chain has moved the task again.
        """
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        layout_task = self.a_task(self.shot, layout)
        self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        cascade = self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )
        back = self.an_automation(
            "shot", "and", [(animation, [self.ready])], layout, self.wip
        )
        later = self.an_automation(
            "shot", "and", [(layout, [self.done])], lighting, self.ready
        )

        self.automations_in_order(cascade, back, later)
        self.comment(layout_task, self.done)

        self.assert_status(layout_task, self.wip)
        self.assert_status(lighting_task, self.ready)

    def test_automations_apply_in_the_order_they_were_created(self):
        """
        The automations a change fires apply in the order they were
        created, whatever the order they were added in: on the same target,
        the last one created sets the status.
        """
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        animation_task = self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        self.an_automation(
            "shot",
            "and",
            [(animation, [self.done])],
            lighting,
            self.ready,
            created_at=datetime.datetime(2026, 1, 2),
        )
        self.an_automation(
            "shot",
            "and",
            [(animation, [self.done])],
            lighting,
            self.wip,
            created_at=datetime.datetime(2026, 1, 1),
        )

        self.comment(animation_task, self.done)

        self.assert_status(lighting_task, self.ready)
        self.assertEqual(
            self.comment_texts(lighting_task),
            ["Change triggered by Animation set to Done"] * 2,
        )

    def test_a_project_lists_its_automations_in_the_order_they_apply(self):
        """
        The order they were created, whatever the order they were added
        in: the settings route and the ids Kitsu reads on the project both
        show it.
        """
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        created, earlier, latest = (
            self.an_automation(
                "shot",
                "and",
                [(animation, [self.done])],
                lighting,
                self.ready,
                created_at=datetime.datetime(2026, 1, day),
            )
            for day in (2, 1, 3)
        )
        expected = [str(earlier.id), str(created.id), str(latest.id)]

        settings = projects_service.get_project_status_automations(
            self.project.id
        )
        project = projects_service.get_project_raw(self.project.id)

        self.assertEqual([row["id"] for row in settings], expected)
        self.assertEqual(
            project.serialize(relations=True)["status_automations"], expected
        )

    def test_the_comment_text_names_the_commented_task(self):
        """
        With two tasks of a condition type, the text gives the status of the
        task the comment changed.
        """
        lighting = self.a_task_type("Lighting")
        fx = self.a_task_type("FX")
        compositing = self.a_task_type("Compositing")
        self.a_task(self.shot, lighting, status=self.done)
        self.a_task(self.shot, fx, "FX a", status=self.na)
        fx_b = self.a_task(self.shot, fx, "FX b", status=self.wip)
        compositing_task = self.a_task(self.shot, compositing)
        self.an_automation(
            "shot",
            "and",
            [(lighting, [self.done]), (fx, [self.done, self.na])],
            compositing,
            self.ready,
        )

        self.comment(fx_b, self.done)

        self.assertEqual(
            self.comment_texts(compositing_task),
            ["Change triggered by Lighting set to Done and FX set to Done"],
        )

    def test_the_priorities_follow_the_entity_type(self):
        """
        Each row reads the priorities of the task types for its own entity
        type, as before conditions. An old row naming an asset type
        ("props") finds none, so it fires whatever the priorities, while an
        "asset" row on the same change does not.
        """
        modeling = self.a_task_type("Modeling", "Asset", priority=1)
        rigging = self.a_task_type("Rigging", "Asset", priority=2)
        concept = self.a_task_type("Concept", "Asset", priority=3)
        concept_task = self.a_task(self.asset, concept)
        modeling_task = self.a_task(self.asset, modeling)
        rigging_task = self.a_task(self.asset, rigging)
        asset_type = EntityType.get(self.asset.entity_type_id).name.lower()
        self.an_automation(
            asset_type, "and", [(concept, [self.done])], modeling, self.wip
        )
        self.an_automation(
            "asset", "and", [(concept, [self.done])], rigging, self.ready
        )

        self.comment(concept_task, self.done)

        self.assert_status(modeling_task, self.wip)
        self.assert_status(rigging_task, self.todo)

    def test_a_chain_into_an_and_trigger_is_no_cycle(self):
        """
        An automation fired down a chain is not fired again by the comment
        that started it, so no cycle is reported.
        """
        layout = self.a_task_type("Layout")
        animation = self.a_task_type("Animation")
        lighting = self.a_task_type("Lighting")
        layout_task = self.a_task(self.shot, layout)
        self.a_task(self.shot, animation)
        lighting_task = self.a_task(self.shot, lighting)
        cascade = self.an_automation(
            "shot", "and", [(layout, [self.done])], animation, self.ready
        )
        both = self.an_automation(
            "shot",
            "and",
            [(layout, [self.done]), (animation, [self.ready])],
            lighting,
            self.ready,
        )

        self.automations_in_order(cascade, both)
        with self.assertNoLogs(current_app.logger, level="WARNING"):
            self.comment(layout_task, self.done)

        self.assert_status(lighting_task, self.ready)
        self.assertEqual(len(self.comment_texts(lighting_task)), 1)

    def test_a_change_the_target_guard_skips_is_no_fire(self):
        """
        Skipped by its target guard, an automation can still apply its
        change later in the same action.
        """
        first = self.a_task_type("First")
        second = self.a_task_type("Second")
        third = self.a_task_type("Third")
        first_task = self.a_task(self.shot, first)
        second_task = self.a_task(self.shot, second, status=self.wip)
        self.a_task(self.shot, third)
        guarded = self.an_automation(
            "shot", "and", [(first, [self.done])], second, self.ready
        )
        guarded.update({"out_only_if_task_status_ids": [str(self.todo.id)]})
        chain = [
            self.an_automation(
                "shot", "and", [(first, [self.done])], second, self.todo
            ),
            self.an_automation(
                "shot", "and", [(second, [self.todo])], first, self.wip
            ),
            self.an_automation(
                "shot", "and", [(first, [self.wip])], third, self.done
            ),
            self.an_automation(
                "shot", "and", [(third, [self.done])], first, self.done
            ),
        ]

        self.automations_in_order(guarded, *chain)
        self.comment(first_task, self.done)

        self.assert_status(first_task, self.done)
        self.assert_status(second_task, self.ready)
