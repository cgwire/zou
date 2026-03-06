from tests.base import ApiDBTestCase

from zou.app.services import concepts_service
from zou.app.services.exception import ConceptNotFoundException


class ConceptsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(ConceptsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()

    def test_create_concept(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept 1"
        )
        self.assertEqual(concept["name"], "Concept 1")
        self.assertEqual(concept["project_id"], str(self.project.id))

    def test_create_concept_with_description(self):
        concept = concepts_service.create_concept(
            str(self.project.id),
            "Concept 2",
            description="A cool concept",
        )
        self.assertEqual(concept["description"], "A cool concept")

    def test_create_concept_idempotent(self):
        concept1 = concepts_service.create_concept(
            str(self.project.id), "Same Name"
        )
        concept2 = concepts_service.create_concept(
            str(self.project.id), "Same Name"
        )
        self.assertEqual(concept1["id"], concept2["id"])

    def test_get_concept_raw(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept Raw"
        )
        raw = concepts_service.get_concept_raw(concept["id"])
        self.assertEqual(str(raw.id), concept["id"])

    def test_get_concept_raw_not_found(self):
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw("wrong-id")

    def test_get_concept(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept Get"
        )
        result = concepts_service.get_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        self.assertEqual(result["name"], "Concept Get")

    def test_get_concepts(self):
        concepts_service.create_concept(
            str(self.project.id), "Concept A"
        )
        concepts_service.create_concept(
            str(self.project.id), "Concept B"
        )
        concepts = concepts_service.get_concepts()
        self.assertEqual(len(concepts), 2)

    def test_get_concepts_for_project(self):
        concepts_service.create_concept(
            str(self.project.id), "Concept P"
        )
        concepts = concepts_service.get_concepts_for_project(
            str(self.project.id)
        )
        self.assertEqual(len(concepts), 1)
        self.assertEqual(concepts[0]["name"], "Concept P")

    def test_get_concepts_and_tasks(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept Tasks"
        )
        result = concepts_service.get_concepts_and_tasks()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Concept Tasks")
        self.assertEqual(result[0]["tasks"], [])

    def test_get_full_concept(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept Full"
        )
        result = concepts_service.get_full_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        self.assertEqual(result["name"], "Concept Full")

    def test_get_full_concept_not_found(self):
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_full_concept(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_remove_concept(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "To Remove"
        )
        result = concepts_service.remove_concept(concept["id"])
        self.assertEqual(result["id"], concept["id"])
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw(concept["id"])

    def test_remove_concept_with_task_cancels(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = concepts_service.create_concept(
            str(self.project.id), "With Task"
        )
        self.generate_fixture_task(
            entity_id=concept["id"],
            task_type_id=self.task_type.id,
        )
        result = concepts_service.remove_concept(concept["id"])
        self.assertTrue(result["canceled"])

    def test_remove_concept_with_task_force(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = concepts_service.create_concept(
            str(self.project.id), "Force Remove"
        )
        self.generate_fixture_task(
            entity_id=concept["id"],
            task_type_id=self.task_type.id,
        )
        result = concepts_service.remove_concept(
            concept["id"], force=True
        )
        self.assertEqual(result["id"], concept["id"])
        with self.assertRaises(ConceptNotFoundException):
            concepts_service.get_concept_raw(concept["id"])

    def test_is_concept(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Is Concept"
        )
        self.assertTrue(concepts_service.is_concept(concept))

        self.generate_fixture_asset()
        asset = self.asset.serialize()
        self.assertFalse(concepts_service.is_concept(asset))
