from tests.blueprints.edits.base import BaseEditTestCase
from zou.app.services import (
    edits_service,
    metadata_descriptors_service,
    persons_service,
    projects_service,
    tasks_service,
)


class EditTasksTestCase(BaseEditTestCase):
    def test_get_tasks_for_edit(self):
        tasks = self.get(f"data/edits/{self.edit.id}/tasks")
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["id"], str(self.task.id))

    def test_get_edit_task_lists_paginated(self):
        edit = self.generate_fixture_edit("Trailer", parent_id=self.episode_id)
        self.generate_fixture_task(
            name="Edit",
            entity_id=edit.id,
            task_type_id=self.task_type_edit.id,
        )
        for path in [
            f"data/edits/{self.edit_id}/tasks",
            f"data/episodes/{self.episode_id}/edit-tasks",
            f"data/episodes/{self.episode_id}/edit-tasks?relations=true",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)
                full = self.assert_pages_match_full_list(path, ordered=False)
                self.assertGreaterEqual(len(full), 2)

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
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}", 403)
        projects_service.add_team_member(project_id, person_id)
        projects_service.clear_project_cache(str(project_id))
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}")
        self.assertEqual(edits, [])
        tasks_service.assign_task(task_id, person_id)
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}")
        self.assertEqual(len(edits), 1)
        self.assertEqual(len(edits[0]["tasks"]), 1)
        self.assertIn(str(person_id), edits[0]["tasks"][0]["assignees"])

        edits_service.update_edit(
            self.edit_id, {"data": {"contractor": "test"}}
        )
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}")
        self.assertEqual(edits[0]["data"]["contractor"], "test")

        metadata_descriptors_service.update_metadata_descriptor(
            self.meta_descriptor_id, {"departments": [self.department_id]}
        )
        persons_service.add_to_department(str(self.department_id), person_id)
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}")
        self.assertEqual(edits[0]["data"]["contractor"], "test")

        persons_service.remove_from_department(
            str(self.department_id), person_id
        )
        edits = self.get(f"data/edits/with-tasks?project_id={project_id}")
        self.assertNotIn("contractor", edits[0]["data"])

        # The listings without the tasks answer the same production, so they
        # hide the same descriptor.
        for path in ["data/edits", "data/edits/all"]:
            with self.subTest(path=path):
                edits = self.get(f"{path}?project_id={project_id}")
                self.assertNotIn("contractor", edits[0]["data"])

    def test_get_edits_and_tasks_paginated(self):
        self.generate_fixture_user_vendor()
        vendor_id = self.user_vendor["id"]
        project_id = str(self.project.id)
        projects_service.add_team_member(project_id, vendor_id)
        projects_service.clear_project_cache(project_id)
        for name in ["Trailer", "Teaser"]:
            edit = self.generate_fixture_edit(name, parent_id=self.episode_id)
            self.generate_fixture_task(
                name="Edit",
                entity_id=edit.id,
                task_type_id=self.task_type_edit.id,
            )
        tasks_service.assign_task(self.task.id, vendor_id)
        path = f"data/edits/with-tasks?project_id={project_id}"
        self.assert_opt_in_pagination(path)
        full = self.assert_pages_match_full_list(path, ordered=False)
        self.assertEqual(len(full), 3)
        self.assert_pages_match_full_list(path, limit=2, ordered=False)

        self.log_in_vendor()
        self.assert_opt_in_pagination(path)
        full = self.assert_pages_match_full_list(path, ordered=False)
        self.assertEqual([edit["name"] for edit in full], ["Teaser"])
        self.assertEqual(len(full[0]["tasks"]), 1)

    def test_get_task_types_for_edit(self):
        task_types = self.get(f"data/edits/{self.edit_id}/task-types")
        self.assertEqual(len(task_types), 1)
        self.assertDictEqual(task_types[0], self.task_type_edit_dict)

    def test_get_task_types_for_edit_not_found(self):
        self.get("data/edits/no-edit/task-types", 404)
