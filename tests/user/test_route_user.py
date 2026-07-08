from tests.base import ApiDBTestCase

from zou.app.services import tasks_service, projects_service
from zou.app.models.person import Person
from zou.app.models.project import Project


class UserRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(UserRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.user_id = self.user["id"]
        tasks_service.assign_task(self.task.id, self.user_id)
        project = Project.get(self.project.id)
        person = Person.get(self.user_id)
        project.team.append(person)
        project.save()

    def test_get_asset_task_types(self):
        result = self.get(f"/data/user/assets/{self.asset.id}/task-types")
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_task_subscription(self):
        path = f"/data/user/tasks/{self.task.id}/subscribed"
        self.assertFalse(self.get(path))
        self.post(f"/actions/user/tasks/{self.task.id}/subscribe", {}, 201)
        self.assertTrue(self.get(path))

    def test_tasks_batch_subscription(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)
        subscribed_task = f"/data/user/tasks/{task_id}/subscribed"
        subscribed_shot_task = f"/data/user/tasks/{shot_task_id}/subscribed"
        self.assertFalse(self.get(subscribed_task))
        self.assertFalse(self.get(subscribed_shot_task))

        result = self.post(
            "/actions/user/tasks/subscribe",
            {"task_ids": [task_id, shot_task_id]},
            201,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue(self.get(subscribed_task))
        self.assertTrue(self.get(subscribed_shot_task))

        self.post(
            "/actions/user/tasks/unsubscribe",
            {"task_ids": [task_id, shot_task_id]},
            200,
        )
        self.assertFalse(self.get(subscribed_task))
        self.assertFalse(self.get(subscribed_shot_task))

    def test_join_and_leave_chat(self):
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        chat = self.get(f"/data/entities/{self.asset.id}/chat")
        self.assertIn(str(self.user_id), chat["participants"])

        self.delete(f"/actions/user/chats/{self.asset.id}/join")
        chat = self.get(f"/data/entities/{self.asset.id}/chat")
        self.assertNotIn(str(self.user_id), chat["participants"])
