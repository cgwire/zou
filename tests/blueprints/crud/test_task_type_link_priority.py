from tests.blueprints.tasks.test_tasks import TaskTestCase
from zou.app.models.project import Project, ProjectTaskTypeLink
from zou.app.models.task_type import TaskType


class TaskTypeLinkTestCase(TaskTestCase):
    def test_update_task_priority(self):
        self.assertEqual(ProjectTaskTypeLink.query.count(), 0)
        self.post(
            "/data/task-type-links",
            {
                "task_type_id": TaskType.query.first().id,
                "project_id": Project.query.first().id,
                "priority": 2,
            },
        )
        self.assertEqual(ProjectTaskTypeLink.query.first().priority, 2)
        self.post(
            "/data/task-type-links",
            {
                "task_type_id": TaskType.query.first().id,
                "project_id": Project.query.first().id,
                "priority": 3,
            },
        )
        self.assertEqual(ProjectTaskTypeLink.query.count(), 1)
        self.assertEqual(ProjectTaskTypeLink.query.first().priority, 3)
