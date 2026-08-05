from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import tasks_service


class RouteBotCollaborationTestCase(ApiDBTestCase):
    """
    Bots are normally forbidden from being assigned to tasks or logging time
    (check_person_is_not_bot). When a project has bot collaboration enabled,
    those operations must be allowed for that project's tasks.
    """

    def setUp(self):
        super(RouteBotCollaborationTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.task_id = str(self.task.id)
        self.bot = Person.create(
            first_name="Dev",
            last_name="Agent",
            email="dev.agent@example.com",
            is_bot=True,
        )
        self.bot_id = str(self.bot.id)

    def enable_bot_collaboration(self):
        self.project.update({"is_bot_collaboration_enabled": True})

    # --- assignment -------------------------------------------------------

    def test_assign_bot_forbidden_by_default(self):
        data = {"person_id": self.bot_id}
        self.put(f"/actions/tasks/{self.task_id}/assign", data, 403)

    def test_assign_bot_allowed_when_enabled(self):
        self.enable_bot_collaboration()
        data = {"person_id": self.bot_id}
        self.put(f"/actions/tasks/{self.task_id}/assign", data, 200)
        task = self.get(f"data/tasks/{self.task_id}")
        self.assertIn(self.bot_id, task["assignees"])

    def test_assign_human_still_allowed(self):
        data = {"person_id": str(self.person.id)}
        self.put(f"/actions/tasks/{self.task_id}/assign", data, 200)

    def test_setting_is_toggleable_via_api(self):
        project_id = str(self.project.id)
        self.put(
            f"/data/projects/{project_id}",
            {"is_bot_collaboration_enabled": True},
            200,
        )
        project = self.get(f"/data/projects/{project_id}")
        self.assertTrue(project["is_bot_collaboration_enabled"])

    # --- time spent -------------------------------------------------------

    def test_add_time_spent_for_bot_allowed_when_enabled(self):
        self.enable_bot_collaboration()
        # Time can only be logged for someone assigned to the task — assign
        # the bot first (the realistic agent workflow).
        self.put(
            f"/actions/tasks/{self.task_id}/assign",
            {"person_id": self.bot_id},
            200,
        )
        data = {"duration": 60}
        self.post(
            f"/actions/tasks/{self.task_id}"
            f"/time-spents/2026-05-31/persons/{self.bot_id}",
            data,
            201,
        )

    def test_add_time_spent_for_bot_forbidden_by_default(self):
        data = {"duration": 60}
        self.post(
            f"/actions/tasks/{self.task_id}"
            f"/time-spents/2026-05-31/persons/{self.bot_id}",
            data,
            403,
        )
