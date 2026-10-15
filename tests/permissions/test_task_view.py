from tests.base import ApiDBTestCase

from zou.app.services import projects_service
from zou.app.utils import fields


class ClientTaskViewTestCase(ApiDBTestCase):
    """
    A client follows where the work stands, not how the studio runs it:
    every task payload keeps its shape, but the assignees, the estimates,
    the dates and the counts come back blank.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        # The shot and sequence fixtures only set assignees.
        for task in (
            self.generate_fixture_shot_task(),
            self.generate_fixture_sequence_task(),
        ):
            task.update(
                {
                    "estimation": 40,
                    "duration": 50,
                    "due_date": fields.get_date_object("2017-02-28"),
                }
            )
        self.generate_fixture_user_client()
        self.project_id = str(self.project.id)
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )

    def assert_blank(self, task):
        self.assertEqual(task["assignees"], [])
        self.assertEqual(task["estimation"], 0)
        self.assertEqual(task["duration"], 0)
        self.assertEqual(task["retake_count"], 0)
        self.assertIsNone(task["due_date"])
        self.assertIsNone(task["start_date"])
        self.assertIsNone(task["real_start_date"])
        # The status and the type are what a client reads of a task.
        self.assertIsNotNone(task["task_status_id"])
        self.assertIsNotNone(task["task_type_id"])

    def assert_full(self, task):
        self.assertEqual(task["assignees"], [str(self.person.id)])
        self.assertEqual(task["estimation"], 40)
        self.assertEqual(task["duration"], 50)
        self.assertIsNotNone(task["due_date"])

    def test_shots_with_tasks(self):
        path = f"data/shots/with-tasks?project_id={self.project_id}"
        self.assert_full(self.get(path)[0]["tasks"][0])
        self.log_in_client()
        self.assert_blank(self.get(path)[0]["tasks"][0])

    def test_shots_with_tasks_compact(self):
        path = (
            f"data/shots/with-tasks?project_id={self.project_id}&compact=true"
        )
        self.log_in_client()
        response = self.get(path)
        fields = response["task_fields"]
        shot_fields = response["shot_fields"]
        row = response["rows"][0][shot_fields.index("tasks")][0]
        task = dict(zip(fields, row))
        self.assert_blank(task)

    def test_assets_with_tasks(self):
        path = f"data/assets/with-tasks?project_id={self.project_id}"
        self.assert_full(self.get(path)[0]["tasks"][0])
        self.log_in_client()
        self.assert_blank(self.get(path)[0]["tasks"][0])

    def test_sequences_with_tasks(self):
        path = f"data/sequences/with-tasks?project_id={self.project_id}"
        self.assertEqual(self.get(path)[0]["tasks"][0]["estimation"], 40)
        self.log_in_client()
        task = self.get(path)[0]["tasks"][0]
        self.assertEqual(task["estimation"], 0)
        self.assertIsNone(task["due_date"])

    def test_tasks_listing(self):
        path = f"data/tasks?project_id={self.project_id}&relations=true"
        self.assert_full(self.get(path)[0])
        self.log_in_client()
        tasks = self.get(path)
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            self.assert_blank(task)

    def test_task_detail(self):
        path = f"data/tasks/{self.task.id}"
        self.assert_full(self.get(path))
        self.log_in_client()
        task = self.get(path)
        self.assert_blank(task)
        self.assertIsNone(task["assigner_id"])

    def test_task_full(self):
        path = f"data/tasks/{self.task.id}/full"
        full = self.get(path)
        self.assert_full(full)
        self.assertEqual(len(full["persons"]), 1)
        self.log_in_client()
        full = self.get(path)
        self.assert_blank(full)
        self.assertEqual(full["persons"], [])
        self.assertNotIn("assigner", full)

    def test_entity_tasks(self):
        for path in (
            f"data/shots/{self.shot.id}/tasks?relations=true",
            f"data/assets/{self.asset.id}/tasks?relations=true",
            f"data/sequences/{self.sequence.id}/tasks?relations=true",
            f"data/sequences/{self.sequence.id}/shot-tasks?relations=true",
        ):
            self.log_in_admin()
            self.assert_full(self.get(path)[0])
            self.log_in_client()
            self.assert_blank(self.get(path)[0])
