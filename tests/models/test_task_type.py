from tests.base import ApiDBTestCase
from zou.app.models.entity_type import EntityType
from zou.app.models.task_type import TaskType
from zou.app.services.assets_service import build_entity_type_asset_type_filter

from zou.app.utils import fields


class TaskTypeTestCase(ApiDBTestCase):
    def setUp(self):
        super(TaskTypeTestCase, self).setUp()
        self.generate_fixture_department()
        self.department_id = self.department.id
        self.generate_fixture_task_type()

    def test_get_task_types(self):
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 6)

    def test_get_task_type(self):
        task_type = self.get_first("data/task-types")
        task_type_again = self.get("data/task-types/%s" % task_type["id"])
        self.assertEqual(task_type, task_type_again)
        self.get_404("data/task-types/%s" % fields.gen_uuid())

    def test_create_task_type(self):
        data = {
            "name": "animation",
            "color": "#000000",
            "department_id": self.department_id,
        }
        self.task_type = self.post("data/task-types", data)
        self.assertIsNotNone(self.task_type["id"])

        # Test to not create twice the same, '400' error code
        self.task_type = self.post("data/task-types", data, 400)

        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 7)

    def test_create_task_type_with_asset_types(self):
        self.generate_fixture_asset_types()
        asset_types = [
            str(asset_type.id) for asset_type in EntityType.query.filter(build_entity_type_asset_type_filter())
        ]
        data = {
            "name": "animation",
            "color": "#000000",
            "department_id": self.department_id,
            "asset_types": asset_types
        }
        self.task_type = self.post("data/task-types", data)
        self.assertIsNotNone(self.task_type["id"])
        self.assertEquals(
            set(self.task_type["asset_types"]),
            set(asset_types),
        )

        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 7)

        created_task_type = TaskType.get(self.task_type["id"])
        self.assertEquals(
            set(
                str(task_type.id) for task_type in created_task_type.asset_types
            ),
            set(asset_types),
        )

    def test_update_task_type(self):
        task_type = self.get_first("data/task-types")
        data = {"color": "#FFFFFF"}
        self.put("data/task-types/%s" % task_type["id"], data)
        task_type_again = self.get("data/task-types/%s" % task_type["id"])
        self.assertEqual(data["color"], task_type_again["color"])
        self.put_404("data/task-types/%s" % fields.gen_uuid(), data)

    def test_update_task_type_with_asset_types(self):
        self.generate_fixture_asset_types()
        task_type = self.get_first("data/task-types")
        asset_types = [
            str(asset_type.id) for asset_type in EntityType.query.filter(build_entity_type_asset_type_filter())
        ]
        data = {
            "name": "layout",
            "asset_types": asset_types
        }
        self.put("data/task-types/%s" % task_type["id"], data)
        task_type_again = self.get("data/task-types/%s" % task_type["id"])
        self.assertEquals(
            set(asset_type for asset_type in task_type_again["asset_types"]),
            set(asset_types),
        )

    def test_delete_task_type(self):
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 6)
        task_type = task_types[0]
        self.delete("data/task-types/%s" % task_type["id"])
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 5)
        self.delete_404("data/task-types/%s" % fields.gen_uuid())
