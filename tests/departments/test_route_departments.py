from tests.base import ApiDBTestCase

from zou.app.models.hardware_item import HardwareItem
from zou.app.services import departments_service


class DepartmentRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(DepartmentRoutesTestCase, self).setUp()
        self.generate_fixture_department()
        self.generate_fixture_software()
        self.hardware_item = HardwareItem.create(
            name="Wacom Tablet", short_name="wacom"
        )

    # --- Software routes ---

    def test_get_all_department_software(self):
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        result = self.get("/data/departments/software-licenses")
        self.assertIn(str(self.department.id), result)
        self.assertEqual(len(result[str(self.department.id)]), 1)

    def test_get_all_department_software_empty(self):
        result = self.get("/data/departments/software-licenses")
        self.assertEqual(len(result), 0)

    def test_add_software_to_department(self):
        result = self.post(
            f"/data/departments/{self.department.id}/software-licenses",
            {"software_id": str(self.software.id)},
        )
        self.assertEqual(result["department_id"], str(self.department.id))
        self.assertEqual(result["software_id"], str(self.software.id))
        software_list = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(software_list), 1)
        self.assertEqual(software_list[0]["name"], "Blender")

    def test_get_department_software(self):
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        result = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Blender")

    def test_delete_software_from_department(self):
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        self.delete(
            f"/data/departments/{self.department.id}"
            f"/software-licenses/{self.software.id}"
        )
        result = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 0)

    # --- Hardware routes ---

    def test_get_all_department_hardware_items(self):
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        result = self.get("/data/departments/hardware-items")
        self.assertIn(str(self.department.id), result)
        self.assertEqual(len(result[str(self.department.id)]), 1)

    def test_get_all_department_hardware_items_empty(self):
        result = self.get("/data/departments/hardware-items")
        self.assertEqual(len(result), 0)

    def test_add_hardware_item_to_department(self):
        result = self.post(
            f"/data/departments/{self.department.id}/hardware-items",
            {"hardware_item_id": str(self.hardware_item.id)},
        )
        self.assertEqual(
            result["department_id"], str(self.department.id)
        )
        self.assertEqual(
            result["hardware_item_id"], str(self.hardware_item.id)
        )
        items = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Wacom Tablet")

    def test_get_department_hardware_items(self):
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        items = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Wacom Tablet")

    def test_delete_hardware_item_from_department(self):
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        self.delete(
            f"/data/departments/{self.department.id}"
            f"/hardware-items/{self.hardware_item.id}"
        )
        result = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 0)
