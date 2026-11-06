import json

from tests.base import ApiDBTestCase
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.status_automation import StatusAutomation
from zou.app.models.task_type import TaskType
from zou.app.utils import fields


class TaskTypeTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_department()
        self.department_id = self.department.id
        self.generate_data(TaskType, 3, department_id=self.department_id)

    def test_get_task_types(self):
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 3)

    def test_get_task_type(self):
        task_type = self.get_first("data/task-types")
        task_type_again = self.get(f"data/task-types/{task_type['id']}")
        self.assertEqual(task_type, task_type_again)
        self.get_404(f"data/task-types/{fields.gen_uuid()}")

    def test_create_task_type(self):
        data = {
            "name": "animation",
            "color": "#000000",
            "department_id": self.department_id,
        }
        self.task_type = self.post("data/task-types", data)
        self.assertIsNotNone(self.task_type["id"])
        self.task_type = self.post("data/task-types", data, 400)

        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 4)

    def test_create_task_type_with_a_name_differing_only_by_case(self):
        """
        A case differing twin makes the task type unresolvable by name in the
        clients, which filter on names, so it is refused like an exact one.
        """
        self.post(
            "data/task-types",
            {
                "name": "compositing",
                "color": "#000000",
                "department_id": self.department_id,
            },
        )
        self.post(
            "data/task-types",
            {
                "name": "COMPOSITING",
                "color": "#000000",
                "department_id": self.department_id,
            },
            400,
        )
        self.assertEqual(len(self.get("data/task-types")), 4)

    def test_rename_task_type_onto_a_name_differing_only_by_case(self):
        self.post(
            "data/task-types",
            {
                "name": "compositing",
                "color": "#000000",
                "department_id": self.department_id,
            },
        )
        other = self.post(
            "data/task-types",
            {
                "name": "layout",
                "color": "#000000",
                "department_id": self.department_id,
            },
        )
        self.put(
            f"data/task-types/{other['id']}", {"name": "COMPOSITING"}, 400
        )

    def test_rename_task_type_keeping_its_own_name_case(self):
        task_type = self.post(
            "data/task-types",
            {
                "name": "compositing",
                "color": "#000000",
                "department_id": self.department_id,
            },
        )
        self.put(f"data/task-types/{task_type['id']}", {"name": "COMPOSITING"})
        self.assertEqual(
            self.get(f"data/task-types/{task_type['id']}")["name"],
            "COMPOSITING",
        )

    def test_rename_task_type_with_a_legacy_case_twin(self):
        """
        Rows predating the guard can already differ only by case. Renaming
        one of them must still see the other, whichever of the two the
        lookup happens to return first, while an update carrying the row's
        own name must go through: the clients send the whole form on a
        colour change.
        """
        first = TaskType.create(
            name="compositing", department_id=self.department_id
        )
        second = TaskType.create(
            name="Compositing", department_id=self.department_id
        )
        self.put(f"data/task-types/{second.id}", {"name": "COMPOSITING"}, 400)
        self.put(f"data/task-types/{first.id}", {"name": "COMPOSITING"}, 400)

        self.put(
            f"data/task-types/{second.id}",
            {"name": "Compositing", "color": "#FFFFFF"},
        )
        self.assertEqual(
            self.get(f"data/task-types/{second.id}")["color"], "#FFFFFF"
        )

    def test_update_task_type(self):
        task_type = self.get_first("data/task-types")
        data = {"color": "#FFFFFF"}
        self.put(f"data/task-types/{task_type['id']}", data)
        task_type_again = self.get(f"data/task-types/{task_type['id']}")
        self.assertEqual(data["color"], task_type_again["color"])
        self.put_404(f"data/task-types/{fields.gen_uuid()}", data)

    def test_delete_task_type(self):
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 3)
        task_type = task_types[0]
        self.delete(f"data/task-types/{task_type['id']}")
        task_types = self.get("data/task-types")
        self.assertEqual(len(task_types), 2)
        self.delete_404(f"data/task-types/{fields.gen_uuid()}")

    def test_delete_task_type_linked_to_project(self):
        self.generate_fixture_project()
        task_type = TaskType.create(
            name="Linked",
            short_name="lnk",
            color="#FFFFFF",
            for_entity="Asset",
            department_id=self.department_id,
        )
        ProjectTaskTypeLink.create(
            project_id=self.project.id, task_type_id=task_type.id
        )
        task_type_id = str(task_type.id)
        # Without force, the link refuses the delete with a clean 400.
        self.delete(f"data/task-types/{task_type_id}", 400)
        self.assertIsNotNone(TaskType.get(task_type_id))
        # With force, the link is purged first so the deletion succeeds.
        self.delete(f"data/task-types/{task_type_id}?force=true")
        self.assertIsNone(TaskType.get(task_type_id))
        self.assertEqual(
            ProjectTaskTypeLink.query.filter_by(
                task_type_id=task_type_id
            ).count(),
            0,
        )

    def test_delete_task_type_used_by_an_automation(self):
        """
        An automation reading or writing the task type refuses its deletion,
        with force too: dropping it would change when the automation fires.
        """
        self.generate_fixture_task_status()
        in_type, out_type, _ = self.get("data/task-types")
        automation = StatusAutomation.create(
            entity_type="asset",
            in_task_type_id=in_type["id"],
            in_task_status_id=self.task_status.id,
            out_field_type="status",
            out_task_type_id=out_type["id"],
            out_task_status_id=self.task_status.id,
            archived=True,
        )

        for task_type in (in_type, out_type):
            result = json.loads(
                self.delete(
                    f"data/task-types/{task_type['id']}?force=true", 400
                )
            )
            self.assertEqual(
                result["message"],
                f"Task type {task_type['name']} is used by 1 status "
                "automation (1 archived). Remove it from that automation "
                "first.",
            )
            self.assertIsNotNone(TaskType.get(task_type["id"]))

        automation.delete()
        self.delete(f"data/task-types/{in_type['id']}")
        self.assertIsNone(TaskType.get(in_type["id"]))
