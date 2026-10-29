from tests.base import ApiDBTestCase
from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.services import projects_service, tasks_service
from zou.app.utils import fields


class TaskTestCase(ApiDBTestCase):
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

    def test_get_tasks(self):
        tasks = self.get("data/tasks")
        self.assertEqual(len(tasks), 3)

    def test_get_task(self):
        task = self.get_first("data/tasks?relations=true")
        task_again = self.get(f"data/tasks/{task['id']}")
        self.assertEqual(task, task_again)
        self.get_404(f"data/tasks/{fields.gen_uuid()}")

    def test_get_tasks_follows_the_role_held_on_the_project(self):
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        projects_service.add_team_member(self.project.id, artist_id, "vendor")
        self.log_in_cg_artist()
        self.assertEqual(self.get("data/tasks"), [])
        tasks_service.assign_task(self.tasks[0].id, artist_id)
        self.assertEqual(len(self.get("data/tasks")), 1)

        projects_service.update_team_member_role(
            self.project.id, artist_id, "client"
        )
        tasks = self.get("data/tasks")
        self.assertEqual(len(tasks), 3)
        self.assertEqual({task["assigner_id"] for task in tasks}, {None})

    def test_create_task(self):
        data = {
            "name": "Modeling arbre",
            "project_id": self.project.id,
            "task_type_id": self.task_type.id,
            "task_status_id": self.task_status.id,
            "entity_id": self.asset.id,
            "assignees": [str(self.person.id)],
            "assigner_id": self.assigner.id,
        }
        self.task = self.post("data/tasks", data)
        self.assertIsNotNone(self.task["id"])
        self.assertEqual(str(self.person.id), self.task["assignees"][0])

        self.assertEqual(len(self.get("data/tasks")), 4)

        # A body carrying no assignees is accepted, the task just has none.
        del data["assignees"]
        data["name"] = "Task without assignees"
        task = self.post("data/tasks", data)
        self.assertEqual(task["assignees"], [])
        self.assertEqual(len(self.get("data/tasks")), 5)

    def test_create_task_without_name_defaults_to_main(self):
        data = {
            "project_id": self.project.id,
            "task_type_id": self.task_type.id,
            "task_status_id": self.task_status.id,
            "entity_id": self.asset.id,
            "assigner_id": self.assigner.id,
        }
        task = self.post("data/tasks", data)
        self.assertEqual(task["name"], "main")

    def test_create_task_refuses_an_incomplete_body(self):
        data = {
            "project_id": self.project.id,
            "task_status_id": self.task_status.id,
            "entity_id": self.asset.id,
        }
        self.post("data/tasks", data, 400)
        data["task_type_id"] = self.task_type.id
        del data["entity_id"]
        self.post("data/tasks", data, 400)
        data["entity_id"] = self.asset.id
        data["assignees"] = str(self.person.id)
        self.post("data/tasks", data, 400)

    def test_create_task_requires_a_manager_of_the_entity_project(self):
        data = {
            "task_type_id": self.task_type.id,
            "task_status_id": self.task_status.id,
            "entity_id": self.asset.id,
        }
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id, self.user_cg_artist["id"]
        )
        self.log_in_manager()
        self.post("data/tasks", data, 403)
        self.log_in_cg_artist()
        self.post("data/tasks", data, 403)

        projects_service.add_team_member(
            self.project.id, self.user_manager["id"]
        )
        self.log_in_manager()
        project_id = str(self.project.id)
        data["project_id"] = self.generate_fixture_project("Other").id
        task = self.post("data/tasks", data)
        self.assertEqual(task["project_id"], project_id)

    def test_update_task(self):
        task = self.get_first("data/tasks")
        data = {"name": "Modeling arbre 2"}
        self.put(f"data/tasks/{task['id']}", data)
        task_again = self.get(f"data/tasks/{task['id']}")
        self.assertEqual(data["name"], task_again["name"])
        self.put_404(f"data/tasks/{fields.gen_uuid()}", data)

    def test_delete_task(self):
        tasks = self.get("data/tasks")
        self.assertEqual(len(tasks), 3)
        task = tasks[0]
        self.delete(f"data/tasks/{task['id']}")
        tasks = self.get("data/tasks")
        self.assertEqual(len(tasks), 2)
        self.delete_404(f"data/tasks/{fields.gen_uuid()}")

    def test_filter_by_assignee(self):
        tasks = self.get(f"data/tasks?assignees={self.person.id}")
        self.assertEqual(len(tasks), 3)

    def test_full_task(self):
        task = self.get(f"data/tasks/{self.tasks[0].id}/full")
        self.assertEqual(task["task_type"]["name"], "Shaders")
        self.assertEqual(task["persons"][0]["first_name"], "John")
        self.assertEqual(task["task_status"]["name"], "Open")
        self.assertEqual(task["project"]["name"], "Cosmos Landromat")
        self.assertEqual(task["entity"]["name"], "Tree")
        self.assertEqual(task["assigner"]["first_name"], "Ema")
