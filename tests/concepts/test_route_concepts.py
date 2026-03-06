from tests.base import ApiDBTestCase

from zou.app.services import concepts_service


class ConceptRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ConceptRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()

    def create_concept(self, name="Test Concept"):
        return concepts_service.create_concept(
            str(self.project.id), name
        )

    def test_get_all_concepts(self):
        self.create_concept("Concept A")
        self.create_concept("Concept B")
        result = self.get("/data/concepts")
        self.assertEqual(len(result), 2)

    def test_get_all_concepts_empty(self):
        result = self.get("/data/concepts")
        self.assertEqual(len(result), 0)

    def test_get_concepts_with_tasks(self):
        self.create_concept("Concept With Tasks")
        result = self.get("/data/concepts/with-tasks")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Concept With Tasks")
        self.assertEqual(result[0]["tasks"], [])

    def test_get_concept(self):
        concept = self.create_concept("Single Concept")
        result = self.get(f"/data/concepts/{concept['id']}")
        self.assertEqual(result["name"], "Single Concept")
        self.assertEqual(result["project_id"], str(self.project.id))

    def test_get_concept_not_found(self):
        self.get_404("/data/concepts/00000000-0000-0000-0000-000000000000")

    def test_delete_concept(self):
        concept = self.create_concept("To Delete")
        self.delete(f"/data/concepts/{concept['id']}")
        concepts = self.get("/data/concepts")
        self.assertEqual(len(concepts), 0)

    def test_delete_concept_with_task_cancels(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.create_concept("Cancel Me")
        self.generate_fixture_task(
            entity_id=concept["id"],
            task_type_id=self.task_type.id,
        )
        self.delete(f"/data/concepts/{concept['id']}")
        all_concepts = self.get("/data/concepts")
        self.assertEqual(len(all_concepts), 1)
        self.assertTrue(all_concepts[0]["canceled"])

    def test_get_concept_task_types(self):
        concept = self.create_concept("Task Types Concept")
        result = self.get(
            f"/data/concepts/{concept['id']}/task-types"
        )
        self.assertEqual(len(result), 0)

    def test_get_concept_task_types_with_task(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.create_concept("With Task Types")
        self.generate_fixture_task(
            entity_id=concept["id"],
            task_type_id=self.task_type.id,
        )
        result = self.get(
            f"/data/concepts/{concept['id']}/task-types"
        )
        self.assertEqual(len(result), 1)

    def test_get_concept_tasks(self):
        concept = self.create_concept("Tasks Concept")
        result = self.get(f"/data/concepts/{concept['id']}/tasks")
        self.assertEqual(len(result), 0)

    def test_get_concept_tasks_with_task(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.create_concept("With Tasks")
        self.generate_fixture_task(
            entity_id=concept["id"],
            task_type_id=self.task_type.id,
        )
        result = self.get(f"/data/concepts/{concept['id']}/tasks")
        self.assertEqual(len(result), 1)

    def test_get_concept_preview_files(self):
        concept = self.create_concept("Preview Concept")
        result = self.get(
            f"/data/concepts/{concept['id']}/preview-files"
        )
        self.assertIsInstance(result, dict)

    def test_get_project_concepts(self):
        self.create_concept("Project Concept")
        result = self.get(
            f"/data/projects/{self.project.id}/concepts"
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Project Concept")

    def test_get_project_concepts_empty(self):
        result = self.get(
            f"/data/projects/{self.project.id}/concepts"
        )
        self.assertEqual(len(result), 0)

    def test_create_concept(self):
        result = self.post(
            f"/data/projects/{self.project.id}/concepts",
            {"name": "New Concept"},
        )
        self.assertEqual(result["name"], "New Concept")
        self.assertEqual(result["project_id"], str(self.project.id))
        fetched = self.get(f"/data/concepts/{result['id']}")
        self.assertEqual(fetched["name"], "New Concept")

    def test_create_concept_with_description(self):
        result = self.post(
            f"/data/projects/{self.project.id}/concepts",
            {"name": "Described", "description": "A cool concept"},
        )
        self.assertEqual(result["description"], "A cool concept")
        fetched = self.get(f"/data/concepts/{result['id']}")
        self.assertEqual(fetched["description"], "A cool concept")
