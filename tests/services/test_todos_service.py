from zou.app.services import (
    comments_service,
    tasks_service,
    task_types_service,
    todos_service,
)
from tests.services.cases import TaskTestCase


class TaskReaderTestCase(TaskTestCase):
    def test_get_tasks_for_project_loads_only_assignee_ids(self):
        with self.collect_statements() as statements:
            tasks = todos_service.get_tasks_for_project(self.project.id)

        assignees = [
            assignee for task in tasks for assignee in task["assignees"]
        ]
        self.assertIn(self.person_id, assignees)
        self.assertTrue(
            all(isinstance(assignee, str) for assignee in assignees)
        )

        person_link_statements = [
            statement
            for statement in statements
            if "task_person_link" in statement.lower()
        ]
        self.assertTrue(person_link_statements)
        for statement in person_link_statements:
            self.assertNotIn("person.password", statement)


class PersonTaskTestCase(TaskTestCase):
    def test_get_person_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            todos_service.get_person_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            len(todos_service.get_person_tasks(self.user["id"], projects)), 1
        )

        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "first comment"
        )
        comments_service.new_comment(
            self.task.id, self.task_status.id, self.person.id, "last comment"
        )

        tasks = todos_service.get_person_tasks(self.person.id, projects)
        tasks = sorted(tasks, key=lambda task: task["task_type_name"])
        self.assertEqual(len(tasks), 2)
        # Animation comes first, so the commented task is the second one.
        self.assertEqual(tasks[1]["last_comment"]["text"], "last comment")
        self.assertEqual(tasks[1]["last_comment"]["person_id"], self.person_id)

    def test_get_person_done_tasks(self):
        projects = [self.project.serialize()]
        self.assertEqual(
            todos_service.get_person_done_tasks(self.user["id"], projects), []
        )

        tasks_service.assign_task(self.task.id, self.user["id"])
        self.assertEqual(
            todos_service.get_person_done_tasks(self.user["id"], projects), []
        )

        done_status = task_types_service.get_or_create_task_status(
            "Done", "done", "#22d160", is_done=True
        )
        tasks_service.update_task(
            self.task.id, {"task_status_id": done_status["id"]}
        )

        self.assertEqual(
            len(
                todos_service.get_person_done_tasks(self.user["id"], projects)
            ),
            1,
        )
