import json

from tests.base import ApiDBTestCase
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task_status import TaskStatus
from zou.app.services import task_types_service
from zou.app.utils import fields


class TaskStatusTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_data(TaskStatus, 3)

    def test_get_task_statuss(self):
        task_statuss = self.get("data/task-status")
        self.assertEqual(len(task_statuss), 3)

    def test_get_task_status(self):
        task_status = self.get_first("data/task-status")
        task_status_again = self.get(f"data/task-status/{task_status['id']}")
        self.assertEqual(task_status, task_status_again)
        self.get_404(f"data/task-status/{fields.gen_uuid()}")

    def test_create_task_status(self):
        data = {"name": "open", "short_name": "open", "color": "#000000"}
        self.task_status = self.post("data/task-status", data)
        self.assertIsNotNone(self.task_status["id"])

        task_statuss = self.get("data/task-status")
        self.assertEqual(len(task_statuss), 4)

    def test_update_task_status(self):
        task_status = self.get_first("data/task-status")
        data = {"color": "#FFFFFF"}
        self.put(f"data/task-status/{task_status['id']}", data)
        task_status_again = self.get(f"data/task-status/{task_status['id']}")
        self.assertEqual(data["color"], task_status_again["color"])
        self.put_404(f"data/task-status/{fields.gen_uuid()}", data)

    def test_delete_task_status(self):
        task_statuss = self.get("data/task-status")
        self.assertEqual(len(task_statuss), 3)
        task_status = task_statuss[0]
        self.delete(f"data/task-status/{task_status['id']}")
        task_statuss = self.get("data/task-status")
        self.assertEqual(len(task_statuss), 2)
        self.delete_404(f"data/task-status/{fields.gen_uuid()}")

    def test_delete_task_status_used_by_an_automation(self):
        """
        The foreign keys of the automation used to refuse the deletion with
        the generic conflict message.
        """
        self.generate_fixture_task_type()
        in_status, out_status, _ = self.get("data/task-status")
        automation = StatusAutomation.create(
            entity_type="asset",
            in_task_type_id=self.task_type_concept.id,
            in_task_status_id=in_status["id"],
            out_field_type="status",
            out_task_type_id=self.task_type_modeling.id,
            out_task_status_id=out_status["id"],
        )

        for task_status in (in_status, out_status):
            result = json.loads(
                self.delete(f"data/task-status/{task_status['id']}", 400)
            )
            self.assertEqual(
                result["message"],
                f"Task status {task_status['name']} is used by 1 status "
                "automation. Remove it from that automation first.",
            )

        automation.delete()
        self.delete(f"data/task-status/{in_status['id']}")
        self.assertIsNone(TaskStatus.get(in_status["id"]))

    def test_update_default_task_status_drops_cached_default(self):
        TaskStatus.query.update({"is_default": False})
        old = TaskStatus.create(
            name="Todo", short_name="todo", color="#000000", is_default=True
        )
        new = TaskStatus.create(
            name="Ready", short_name="rdy", color="#000000"
        )
        self.assertEqual(
            task_types_service.get_default_task_status()["id"], str(old.id)
        )
        self.put(f"data/task-status/{new.id}", {"is_default": True})
        self.assertEqual(
            task_types_service.get_default_task_status()["id"], str(new.id)
        )
