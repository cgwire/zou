from tests.base import ApiDBTestCase
from zou.app.services import (
    concepts_service,
    projects_service,
    tasks_service,
)
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
        task = self.get(path)[0]["tasks"][0]
        self.assertEqual(task["estimation"], 40)
        self.assertEqual(task["assignees"], [str(self.person.id)])
        self.log_in_client()
        task = self.get(path)[0]["tasks"][0]
        self.assertEqual(task["estimation"], 0)
        self.assertIsNone(task["due_date"])
        self.assertEqual(task["assignees"], [])

    def test_tasks_listing(self):
        path = f"data/tasks?project_id={self.project_id}&relations=true"
        self.assert_full(self.get(path)[0])
        self.log_in_client()
        tasks = self.get(path)
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            self.assert_blank(task)

    def test_project_tasks(self):
        path = f"data/projects/{self.project_id}/tasks"
        task_id = str(self.task.id)
        self.assert_full(
            next(task for task in self.get(path) if task["id"] == task_id)
        )
        self.log_in_client()
        tasks = self.get(path)
        self.assertEqual(len(tasks), 3)
        for task in tasks:
            self.assert_blank(task)
        page = self.get(f"{path}?page=1")["data"]
        self.assertEqual(len(page), 3)
        for task in page:
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

    def entity_detail_paths(self):
        edit_task = self.generate_fixture_edit_task()
        edit_task.update(
            {
                "estimation": 40,
                "duration": 50,
                "due_date": fields.get_date_object("2017-02-28"),
            }
        )
        return [
            f"data/shots/{self.shot.id}",
            f"data/assets/{self.asset.id}",
            f"data/edits/{self.edit.id}",
        ]

    def get_single_task(self, path):
        tasks = self.get(path)["tasks"]
        self.assertEqual(len(tasks), 1)
        return tasks[0]

    def test_entity_details_when_a_client_comes_first(self):
        """
        The shot, asset and edit payloads are cached the same for every
        role: each caller gets their own shape, whoever filled the cache.
        """
        for path in self.entity_detail_paths():
            with self.subTest(path):
                self.log_in_client()
                self.assert_blank(self.get_single_task(path))
                self.log_in_admin()
                self.assert_full(self.get_single_task(path))

    def test_entity_details_when_the_studio_comes_first(self):
        for path in self.entity_detail_paths():
            with self.subTest(path):
                self.log_in_admin()
                self.assert_full(self.get_single_task(path))
                self.log_in_client()
                self.assert_blank(self.get_single_task(path))

    def test_entity_detail_of_a_client_on_the_project(self):
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        self.assert_blank(self.get_single_task(f"data/shots/{self.shot.id}"))

    def test_concept_detail_after_a_refused_client(self):
        concept = concepts_service.create_concept(self.project_id, "Concept")
        self.generate_fixture_task(name="Concept", entity_id=concept["id"])
        path = f"data/concepts/{concept['id']}"
        self.log_in_client()
        self.get(path, 403)
        self.log_in_admin()
        self.assert_full(self.get_single_task(path))

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


class TaskFullPersonsTestCase(ApiDBTestCase):
    """
    The task page embeds the assignees and the assigner of the task, shaped
    as the person routes shape them: whole for managers, minimal for the
    other studio roles.
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
        self.generate_fixture_task()
        self.path = f"data/tasks/{self.task.id}/full"
        for user in (
            self.generate_fixture_user_manager(),
            self.generate_fixture_user_supervisor(),
            self.generate_fixture_user_cg_artist(),
            self.generate_fixture_user_vendor(),
        ):
            projects_service.add_team_member(str(self.project.id), user["id"])
        # A vendor only reaches the entities they hold a task on.
        tasks_service.assign_task(self.task.id, self.user_vendor["id"])
        self.assignee_ids = sorted(
            [str(self.person.id), self.user_vendor["id"]]
        )

    def test_managers_get_the_whole_persons(self):
        self.log_in_manager()
        task = self.get(self.path)
        self.assertIn("email", task["assigner"])
        self.assertEqual(
            sorted(person["id"] for person in task["persons"]),
            self.assignee_ids,
        )
        for person in task["persons"]:
            self.assertIn("email", person)

    def test_other_roles_get_the_minimal_persons(self):
        minimal_fields = set(self.assigner.present_minimal(relations=True))
        for log_in in (
            self.log_in_supervisor,
            self.log_in_cg_artist,
            self.log_in_vendor,
        ):
            with self.subTest(log_in.__name__):
                log_in()
                task = self.get(self.path)
                self.assertEqual(task["assigner"]["id"], str(self.assigner.id))
                self.assertEqual(set(task["assigner"]), minimal_fields)
                self.assertEqual(
                    sorted(person["id"] for person in task["persons"]),
                    self.assignee_ids,
                )
                for person in task["persons"]:
                    self.assertEqual(set(person), minimal_fields)

    def get_as(self, user, project_role):
        projects_service.add_team_member(
            str(self.project.id), user["id"], role=project_role
        )
        self.log_in(user["email"])
        return self.get(self.path)

    def test_admins_get_the_whole_persons(self):
        task = self.get(self.path)
        self.assertIn("email", task["assigner"])
        for person in task["persons"]:
            self.assertIn("email", person)

    def test_the_role_on_the_project_shapes_the_persons(self):
        task = self.get_as(self.user_manager, "user")
        self.assertNotIn("email", task["assigner"])
        for person in task["persons"]:
            self.assertNotIn("email", person)

    def test_a_manager_on_the_project_gets_the_whole_persons(self):
        task = self.get_as(self.user_supervisor, "manager")
        self.assertIn("email", task["assigner"])
        for person in task["persons"]:
            self.assertIn("email", person)

    def test_a_client_on_the_project_gets_no_persons(self):
        task = self.get_as(self.user_manager, "client")
        self.assertEqual(task["persons"], [])
        self.assertNotIn("assigner", task)
