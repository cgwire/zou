from tests.base import ApiDBTestCase

from zou.app.models.entity_type import EntityType
from zou.app.models.task_type import TaskType

from zou.app.utils import fields


class EntityTypeTestCase(ApiDBTestCase):
    def setUp(self):
        super(EntityTypeTestCase, self).setUp()
        self.generate_fixture_asset_types()

    def test_get_entity_types(self):
        entity_types = self.get("data/entity-types")
        self.assertEqual(len(entity_types), 3)

    def test_get_entity_types_again(self):
        entity_types = self.get_first("data/entity-types?relations=true")
        entity_types_again = self.get(
            "data/entity-types/%s" % entity_types["id"]
        )
        self.assertEqual(entity_types, entity_types_again)
        self.get_404("data/entity-types/%s" % fields.gen_uuid())

    def test_create_entity_types(self):
        data = {"name": "shot"}
        self.asset_types = self.post("data/entity-types", data)
        self.assertIsNotNone(self.asset_types["id"])

        entity_types = self.get("data/entity-types")
        self.assertEqual(len(entity_types), 4)

    def test_create_asset_type_with_task_types(self):
        self.generate_fixture_department()
        self.department_id = self.department.id
        self.generate_fixture_task_type()

        task_types = [str(task_type.id) for task_type in TaskType.query.all()]
        task_types = [
            str(self.task_type_concept.id),
            str(self.task_type_modeling.id),
        ]

        data = {"name": "FX", "task_types": task_types}
        self.asset_type = self.post("data/entity-types", data)
        self.assertIsNotNone(self.asset_type["id"])
        self.assertEqual(
            set(self.asset_type["task_types"]),
            set(task_types),
        )

        asset_types = self.get("data/entity-types")
        self.assertEqual(len(asset_types), 4)

        created_asset_type = EntityType.get(self.asset_type["id"])
        self.assertEqual(
            set(
                str(task_type.id)
                for task_type in created_asset_type.task_types
            ),
            set(task_types),
        )

    def test_update_entity_types(self):
        entity_types = self.get_first("data/entity-types")
        data = {"name": "sequence"}
        self.put("data/entity-types/%s" % entity_types["id"], data)
        entity_types_again = self.get(
            "data/entity-types/%s" % entity_types["id"]
        )
        self.assertEqual(data["name"], entity_types_again["name"])
        self.put_404("data/entity-types/%s" % fields.gen_uuid(), data)

    def test_update_asset_type_with_task_types(self):
        self.generate_fixture_department()
        self.department_id = self.department.id
        self.generate_fixture_task_type()

        asset_type = self.get_first("data/entity-types")
        task_types = [str(task_type.id) for task_type in TaskType.query.all()]
        data = {"name": "FX", "task_types": task_types}
        self.put("data/entity-types/%s" % asset_type["id"], data)
        asset_type_again = self.get("data/entity-types/%s" % asset_type["id"])
        self.assertEqual(
            set(task_type for task_type in asset_type_again["task_types"]),
            set(task_types),
        )

    def test_delete_entity_types(self):
        entity_types = self.get("data/entity-types")
        self.assertEqual(len(entity_types), 3)
        entity_types = entity_types[0]
        self.delete("data/entity-types/%s" % entity_types["id"])
        entity_types = self.get("data/entity-types")
        self.assertEqual(len(entity_types), 2)
        self.delete_404("data/entity-types/%s" % fields.gen_uuid())
