from .base import BaseEditTestCase
from zou.app.services import projects_service, tasks_service


class EditTasksTestCase(BaseEditTestCase):
    def test_get_tasks_for_edit(self):
        tasks = self.get("data/edits/%s/tasks" % self.edit.id)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], str(self.task.id))

    def test_get_edits_and_tasks(self):
        self.generate_fixture_task(name="Secondary", entity_id=self.edit_id)
        edits = self.get("data/edits/with-tasks")
        self.assertEqual(len(edits), 1)
        self.assertEqual(len(edits[0]["tasks"]), 3)
        self.assertEqual(
            edits[0]["tasks"][0]["assignees"][0], str(self.person_id)
        )

    def test_get_edits_and_tasks_vendor(self):
        self.generate_fixture_task(name="Secondary", entity_id=self.edit_id)
        self.generate_fixture_user_vendor()
        task_id = self.task.id
        project_id = self.project.id
        person_id = self.user_vendor["id"]
        self.log_in_vendor()
        edits = self.get(
            "data/edits/with-tasks?project_id=%s" % project_id, 403
        )
        projects_service.add_team_member(project_id, person_id)
        projects_service.clear_project_cache(str(project_id))
        edits = self.get("data/edits/with-tasks?project_id=%s" % project_id)
        self.assertEqual(len(edits), 0)
        tasks_service.assign_task(task_id, person_id)
        edits = self.get("data/edits/with-tasks?project_id=%s" % project_id)
        self.assertEqual(len(edits), 1)
        self.assertEqual(len(edits[0]["tasks"]), 1)
        self.assertTrue(str(person_id) in edits[0]["tasks"][0]["assignees"])

    def test_get_task_types_for_edit(self):
        task_types = self.get("data/edits/%s/task-types" % self.edit_id)
        self.assertEqual(len(task_types), 1)
        self.assertDictEqual(task_types[0], self.task_type_edit_dict)

    def test_get_task_types_for_edit_not_found(self):
        self.get("data/edits/no-edit/task-types", 404)
