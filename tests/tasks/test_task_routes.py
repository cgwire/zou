from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.services import (
    concepts_service,
    persons_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import fields


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
        result = self.get(f"/data/projects/{self.project_id}/subscriptions")
        self.assertIsInstance(result, list)

    def test_get_persons_task_dates(self):
        # Admin gets the studio-wide view.
        result = self.get("/data/persons/task-dates")
        self.assertIsInstance(result, list)
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_as_manager(self):
        # A manager who is a team member of the project sees its persons.
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()
        result = self.get("/data/persons/task-dates")
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_manager_scoped_to_own_projects(self):
        # A manager who belongs to no project sees no one (the default view is
        # scoped to the caller's projects, not studio-wide).
        self.generate_fixture_user_manager()
        self.log_in_manager()
        result = self.get("/data/persons/task-dates")
        self.assertEqual(result, [])

    def test_get_persons_task_dates_manager_own_project_id(self):
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()
        result = self.get(
            f"/data/persons/task-dates?project_id={self.project_id}"
        )
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_manager_foreign_project_id(self):
        # A manager cannot reach a project they are not a team member of.
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.generate_fixture_project_standard()
        self.log_in_manager()
        self.get(
            f"/data/persons/task-dates?project_id={self.project_standard.id}",
            403,
        )

    def test_get_persons_task_dates_admin_project_id(self):
        # Admin can scope the studio-wide view to a single project.
        result = self.get(
            f"/data/persons/task-dates?project_id={self.project_id}"
        )
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_manager_excludes_foreign_persons(self):
        # A manager only sees persons from their own projects, never a person
        # whose tasks live solely in a project they are not a member of.
        person_id = str(self.person.id)
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.generate_fixture_asset_standard()
        foreign_person = Person.create(
            first_name="Foreign",
            last_name="Artist",
            email="foreign.artist@gmail.com",
        )
        Task.create(
            name="Foreign task",
            project_id=self.project_standard.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset_standard.id,
            assignees=[foreign_person],
            assigner_id=self.assigner.id,
            start_date=fields.get_date_object("2017-02-20"),
            due_date=fields.get_date_object("2017-02-28"),
        )
        self.log_in_manager()
        result = self.get("/data/persons/task-dates")
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(person_id, person_ids)
        self.assertNotIn(str(foreign_person.id), person_ids)

    def test_get_persons_task_dates_empty_project_id(self):
        # An empty `?project_id=` filter is treated as absent, not as an
        # invalid UUID (regression: 500 for admins, 404 for managers).
        result = self.get("/data/persons/task-dates?project_id=")
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()
        result = self.get("/data/persons/task-dates?project_id=")
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_invalid_project_id(self):
        # A non-empty, non-UUID `project_id` is rejected with a 400 (before the
        # role branch), instead of reaching the query as an invalid UUID (which
        # used to 500 for admins and 404 for managers).
        self.get("/data/persons/task-dates?project_id=not-a-uuid", 400)
        # Whitespace-only is normalised away like an empty filter, not a 400.
        result = self.get("/data/persons/task-dates?project_id=%20")
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(self.person.id), person_ids)

    def test_get_persons_task_dates_manager_closed_project_id(self):
        # A manager who is a team member of a CLOSED project can still pull its
        # persons when scoping explicitly to it: an access-checked project_id is
        # honoured directly, not intersected with the open-project list (which
        # would drop the closed project and return an empty result).
        self.generate_fixture_user_manager()
        self.generate_fixture_project_closed()
        projects_service.add_team_member(
            str(self.project_closed.id), self.user_manager["id"]
        )
        closed_person = Person.create(
            first_name="Closed",
            last_name="Artist",
            email="closed.artist@gmail.com",
        )
        Task.create(
            name="Closed task",
            project_id=self.project_closed.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[closed_person],
            assigner_id=self.assigner.id,
            start_date=fields.get_date_object("2017-02-20"),
            due_date=fields.get_date_object("2017-02-28"),
        )
        self.log_in_manager()
        result = self.get(
            f"/data/persons/task-dates?project_id={self.project_closed.id}"
        )
        person_ids = [entry["person_id"] for entry in result]
        self.assertIn(str(closed_person.id), person_ids)

    def test_get_persons_task_dates_supervisor_unauthorized(self):
        # The gate is manager-or-above: a supervisor is rejected.
        self.generate_fixture_user_supervisor()
        self.log_in_supervisor()
        self.get("/data/persons/task-dates", 403)

    def test_get_persons_task_dates_unauthorized(self):
        self.generate_fixture_user_vendor()
        self.log_in_vendor()
        self.get("/data/persons/task-dates", 403)

    def test_supervisor_in_department_can_update_task_data(self):
        # A supervisor may write task metadata (task.data) when the task
        # type's department is one of theirs.
        self.generate_fixture_user_supervisor()
        supervisor_id = self.user_supervisor["id"]
        projects_service.add_team_member(self.project_id, supervisor_id)
        persons_service.add_to_department(
            str(self.department.id), supervisor_id
        )
        self.log_in_supervisor()
        self.put(
            f"/data/tasks/{self.task.id}",
            {"data": {"render_engine": "cycles"}},
        )
        task = tasks_service.get_task(str(self.task.id))
        self.assertEqual(task["data"]["render_engine"], "cycles")

    def test_supervisor_outside_department_cannot_update_task_data(self):
        # A supervisor whose departments do not include the task type's
        # department is denied.
        self.generate_fixture_user_supervisor()
        supervisor_id = self.user_supervisor["id"]
        projects_service.add_team_member(self.project_id, supervisor_id)
        persons_service.add_to_department(
            str(self.department_animation.id), supervisor_id
        )
        self.log_in_supervisor()
        self.put(
            f"/data/tasks/{self.task.id}",
            {"data": {"render_engine": "cycles"}},
            403,
        )

    def test_assign_person_to_tasks(self):
        result = self.put(
            f"/actions/persons/{self.person.id}/assign",
            {"task_ids": [str(self.task.id)]},
        )
        self.assertIsInstance(result, list)
        task = tasks_service.get_task(str(self.task.id), relations=True)
        self.assertIn(str(self.person.id), task.get("assignees", []))

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
        task = tasks_service.get_task(str(self.task.id))
        self.assertNotIn(str(self.person.id), task.get("assignees", []))

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
        self.assertTrue(len(result) > 0)

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
        self.assertTrue(len(result) > 0)

    def test_set_main_preview(self):
        self.generate_fixture_preview_file()
        result = self.put(
            f"/actions/tasks/{self.task.id}/set-main-preview",
            {},
        )
        self.assertIsNotNone(result)
        task = tasks_service.get_task(str(self.task.id))
        entity = self.get(f"/data/entities/{task['entity_id']}")
        self.assertIsNotNone(entity.get("preview_file_id"))

    def test_set_main_preview_without_preview(self):
        result = self.put(
            f"/actions/tasks/{self.task.id}/set-main-preview",
            {},
            400,
        )
        self.assertIn("no preview file", result["message"])

    def test_set_main_preview_as_client(self):
        # A client can review but must not redefine the entity thumbnail.
        self.generate_fixture_preview_file()
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()
        self.put(
            f"/actions/tasks/{self.task.id}/set-main-preview",
            {},
            403,
        )

    def test_set_tasks_main_preview(self):
        self.generate_fixture_preview_file(task_id=self.task.id)
        self.generate_fixture_shot_task()
        self.generate_fixture_preview_file(task_id=self.shot_task.id)
        task_ids = [str(self.task.id), str(self.shot_task.id)]
        result = self.put(
            "/actions/tasks/set-main-preview",
            {"task_ids": task_ids},
        )
        self.assertEqual(len(result), 2)
        for task_id in task_ids:
            task = tasks_service.get_task(task_id)
            entity = self.get(f"/data/entities/{task['entity_id']}")
            self.assertIsNotNone(entity.get("preview_file_id"))

    def test_set_tasks_main_preview_as_client(self):
        # A client can review but must not redefine entity thumbnails.
        self.generate_fixture_preview_file()
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()
        self.put(
            "/actions/tasks/set-main-preview",
            {"task_ids": [str(self.task.id)]},
            403,
        )

    def test_delete_tasks_for_task_type(self):
        self.delete(
            f"/actions/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}/delete-tasks"
        )
        self.get_404(f"/data/tasks/{self.task.id}")

    def test_delete_tasks(self):
        shot_task_id = str(self.shot_task.id)
        result = self.post(
            f"/actions/projects/{self.project_id}/delete-tasks",
            [shot_task_id],
            200,
        )
        self.assertIsInstance(result, list)
        self.get_404(f"/data/tasks/{shot_task_id}")

    def test_delete_preview_from_comment(self):
        self.generate_fixture_preview_file()
        self.generate_fixture_comment()
        preview_id = str(self.preview_file.id)
        comment_id = self.comment["id"]
        self.delete(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{comment_id}"
            f"/preview-files/{preview_id}",
        )
        comment = tasks_service.get_comment(comment_id)
        preview_ids = [p["id"] for p in comment.get("previews", [])]
        self.assertNotIn(preview_id, preview_ids)
