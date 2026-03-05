from tests.base import ApiDBTestCase

from zou.app.services import concepts_service, tasks_service


class TaskRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(TaskRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.project_id = str(self.project.id)

    def test_get_open_tasks_stats(self):
        result = self.get("/data/tasks/open-tasks/stats")
        self.assertIsInstance(result, dict)

    def test_get_project_subscriptions(self):
        result = self.get(
            f"/data/projects/{self.project_id}/subscriptions"
        )
        self.assertIsInstance(result, list)

    def test_get_persons_task_dates(self):
        result = self.get("/data/persons/task-dates")
        self.assertIsInstance(result, list)

    def test_assign_person_to_tasks(self):
        result = self.put(
            f"/actions/persons/{self.person.id}/assign",
            {"task_ids": [str(self.task.id)]},
        )
        self.assertIsInstance(result, list)

    def test_clear_assignation(self):
        tasks_service.assign_task(self.task.id, self.person.id)
        result = self.put(
            "/actions/tasks/clear-assignation",
            {
                "task_ids": [str(self.task.id)],
                "person_id": str(self.person.id),
            },
        )
        self.assertIsInstance(result, list)

    def test_create_edit_tasks(self):
        self.generate_fixture_edit()
        result = self.post(
            f"/actions/projects/{self.project_id}"
            f"/task-types/{self.task_type_edit.id}"
            f"/edits/create-tasks",
            {},
            201,
        )
        self.assertIsInstance(result, list)

    def test_create_concept_tasks(self):
        concept = concepts_service.create_concept(
            self.project_id, "Test Concept"
        )
        result = self.post(
            f"/actions/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}"
            f"/concepts/create-tasks",
            {},
            201,
        )
        self.assertIsInstance(result, list)

    def test_set_main_preview(self):
        self.generate_fixture_preview_file()
        result = self.put(
            f"/actions/tasks/{self.task.id}/set-main-preview",
            {},
        )
        self.assertIsNotNone(result)

    def test_delete_tasks_for_task_type(self):
        self.delete(
            f"/actions/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}/delete-tasks"
        )

    def test_delete_tasks(self):
        result = self.post(
            f"/actions/projects/{self.project_id}/delete-tasks",
            [str(self.shot_task.id)],
            200,
        )
        self.assertIsInstance(result, list)

    def test_delete_preview_from_comment(self):
        self.generate_fixture_preview_file()
        self.generate_fixture_comment()
        preview_id = str(self.preview_file.id)
        comment_id = self.comment["id"]
        self.delete(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{comment_id}"
            f"/preview-files/{preview_id}",
            200,
        )
