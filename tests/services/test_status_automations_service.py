# -*- coding: UTF-8 -*-
from flask import current_app

from tests.base import ApiDBTestCase
from zou.app.exceptions import (
    StatusAutomationNotFoundException,
    WrongParameterException,
)
from zou.app.models.entity import Entity
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType
from zou.app.services import (
    comments_service,
    projects_service,
    status_automations_service,
    task_types_service,
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
