from unittest.mock import patch

from tests.base import ApiDBTestCase
from zou.app.exceptions import (
    ConceptNotFoundException,
    EntityNotFoundException,
    WrongIdFormatException,
)
from zou.app.models.entity import Entity
from zou.app.models.task import Task
from zou.app.services import (
    concepts_service,
    persons_service,
)
from zou.app.utils import fields


class ConceptsServiceTestCase(ApiDBTestCase):
    """
    Concepts are entities of their own type, so most of what is checked here
    is that they are told apart from the assets and shots beside them.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()

    def a_concept(self, name, project=None, **kwargs):
        return concepts_service.create_concept(
            str((project or self.project).id), name, **kwargs
        )

    def a_concept_with_a_task(self, name):
        """
        A concept and one task on it, with the whole chain a task needs.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.a_concept(name)
        task = self.generate_fixture_task(
            entity_id=concept["id"], task_type_id=self.task_type.id
        )
        return concept, task

    def test_create_concept_reuses_the_name_within_a_production(self):
        first = self.a_concept("Same Name")

        again = self.a_concept("Same Name")

        self.assertEqual(again["id"], first["id"])

    def test_create_concept_is_free_to_repeat_a_name_elsewhere(self):
        first = self.a_concept("Same Name")
        elsewhere = self.generate_fixture_project_standard()

        other = self.a_concept("Same Name", project=elsewhere)

        self.assertNotEqual(other["id"], first["id"])

    def test_get_concept_raw(self):
        concept = self.a_concept("Concept Raw")
        raw = concepts_service.get_concept_raw(concept["id"])
        self.assertEqual(str(raw.id), concept["id"])

    def test_get_concept_raw_not_found(self):
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw("wrong-id")

    def test_get_concept(self):
        concept = self.a_concept("Concept Get")
        result = concepts_service.get_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        self.assertEqual(result["name"], "Concept Get")

    def test_get_concepts(self):
        """
        Every concept of every production, by name, carrying the name of the
        production it belongs to. An asset is not one of them.
        """
        self.a_concept("Concept B")
        self.a_concept("Concept A")
        self.generate_fixture_asset()

        concepts = concepts_service.get_concepts()

        self.assertEqual(
            [
                (concept["name"], concept["project_name"])
                for concept in concepts
            ],
            [
                ("Concept A", self.project.name),
                ("Concept B", self.project.name),
            ],
        )

    def test_get_concepts_with_criterions(self):
        here = self.a_concept("Here")
        elsewhere = self.generate_fixture_project_standard()
        self.a_concept("Elsewhere", project=elsewhere)

        concepts = concepts_service.get_concepts(
            {"project_id": str(self.project.id)}
        )

        self.assertEqual([concept["id"] for concept in concepts], [here["id"]])

    def test_get_concepts_for_project(self):
        concept = self.a_concept("Concept P")
        elsewhere = self.generate_fixture_project_standard()
        self.a_concept("Elsewhere", project=elsewhere)
        self.generate_fixture_asset()

        concepts = concepts_service.get_concepts_for_project(
            str(self.project.id)
        )

        self.assertEqual([held["id"] for held in concepts], [concept["id"]])

    def test_get_concepts_and_tasks(self):
        concept, task = self.a_concept_with_a_task("Concept Tasks")
        bare = self.a_concept("Concept Bare")

        result = concepts_service.get_concepts_and_tasks()

        tasks_by_concept = {
            held["id"]: [entry["id"] for entry in held["tasks"]]
            for held in result
        }
        self.assertEqual(
            tasks_by_concept,
            {concept["id"]: [str(task.id)], bare["id"]: []},
        )

    def test_get_concepts_and_tasks_carries_the_preview_status(self):
        concept, task = self.a_concept_with_a_task("Concept Processing")
        bare = self.a_concept("Concept Bare")
        preview_file = self.generate_fixture_preview_file(
            status="processing", task_id=task.id
        )
        Entity.get(concept["id"]).update({"preview_file_id": preview_file.id})

        result = concepts_service.get_concepts_and_tasks()

        statuses = {held["id"]: held["preview_file_status"] for held in result}
        self.assertEqual(
            statuses, {concept["id"]: "processing", bare["id"]: None}
        )
        # A raw Choice compares equal to its code but is sent as its label.
        self.assertIsInstance(statuses[concept["id"]], str)

    def test_get_full_concept(self):
        concept = self.a_concept("Concept Full")
        result = concepts_service.get_full_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        self.assertEqual(result["name"], "Concept Full")

    def test_get_full_concept_not_found(self):
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_full_concept(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_the_assigned_concepts_are_the_ones_with_a_task_of_the_user(self):
        """
        The caller comes from the request context, which a service test has
        none of: the assignee filter points at the person of the task.
        """
        concept, _ = self.a_concept_with_a_task("Assigned")
        self.a_concept("Not Assigned")

        with patch.object(
            persons_service,
            "build_assignee_filter",
            side_effect=lambda: Task.assignees.contains(
                persons_service.get_person_raw(self.person.id)
            ),
        ):
            concepts = concepts_service.get_concepts({"assigned_to": True})
            concepts_and_tasks = concepts_service.get_concepts_and_tasks(
                {"assigned_to": True}
            )

        self.assertEqual([held["id"] for held in concepts], [concept["id"]])
        self.assertEqual(
            [held["id"] for held in concepts_and_tasks], [concept["id"]]
        )

    def test_create_concept_keeps_its_data_and_existing_links(self):
        """
        A linked ID that matches no entity is skipped, the others are
        listed on the concept.
        """
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()

        concept = self.a_concept(
            "Linked",
            data={"mood": "dark"},
            entity_concept_links=[str(self.asset.id), fields.gen_uuid()],
        )

        self.assertEqual(concept["data"], {"mood": "dark"})
        held = concepts_service.get_concepts_and_tasks({"id": concept["id"]})[
            0
        ]
        self.assertEqual(held["entity_concept_links"], [str(self.asset.id)])

    def test_create_concept_refuses_a_malformed_link_id(self):
        with self.assertRaises(EntityNotFoundException):
            self.a_concept("Bad Link", entity_concept_links=["not-an-id"])

    def test_move_concepts_refuses_a_malformed_id(self):
        with self.assertRaises(WrongIdFormatException):
            concepts_service.move_concepts(str(self.project.id), ["not-an-id"])
