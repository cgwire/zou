from tests.base import ApiDBTestCase
from zou.app.models.person import Person
from zou.app.models.task import Task


class FullTaskRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.assigner = Person(first_name="Ema", last_name="Peel")
        self.assigner.save()
        self.tasks = self.generate_data(
            Task,
            3,
            entities_out=[],
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )

    def test_full_task(self):
        task = self.get(f"data/tasks/{self.tasks[0].id}/full")
        self.assertEqual(task["task_type"]["name"], "Shaders")
        self.assertEqual(task["persons"][0]["first_name"], "John")
        self.assertEqual(task["task_status"]["name"], "Open")
        self.assertEqual(task["project"]["name"], "Cosmos Landromat")
        self.assertEqual(task["entity"]["name"], "Tree")
        self.assertEqual(task["assigner"]["first_name"], "Ema")
