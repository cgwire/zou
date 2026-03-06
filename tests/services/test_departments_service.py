from tests.base import ApiDBTestCase

from zou.app.models.department import Department
from zou.app.models.software import Software
from zou.app.models.hardware_item import HardwareItem
from zou.app.services.exception import (
    DepartmentNotFoundException,
    SoftwareNotFoundException,
    HardwareItemNotFoundException,
)

from zou.app.services import departments_service


class DepartmentsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(DepartmentsServiceTestCase, self).setUp()

        self.generate_fixture_department()
        self.generate_fixture_software()
        self.hardware_item = HardwareItem.create(
            name="Wacom Tablet", short_name="wacom"
        )
        self.hardware_item_2 = HardwareItem.create(
            name="GPU RTX", short_name="gpu"
        )

    def test_get_software_for_department(self):
        result = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 0)

        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        result = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Blender")

    def test_get_software_for_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.get_software_for_department(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_get_hardware_items_for_department(self):
        result = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 0)

        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        result = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Wacom Tablet")

    def test_get_hardware_items_for_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.get_hardware_items_for_department(
                "00000000-0000-0000-0000-000000000000"
            )

    def test_add_software_to_department(self):
        result = departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        self.assertEqual(
            result["department_id"], str(self.department.id)
        )
        self.assertEqual(
            result["software_id"], str(self.software.id)
        )

    def test_add_software_to_department_idempotent(self):
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        result = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 1)

    def test_add_software_to_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.add_software_to_department(
                "00000000-0000-0000-0000-000000000000", str(self.software.id)
            )
        with self.assertRaises(SoftwareNotFoundException):
            departments_service.add_software_to_department(
                str(self.department.id), "00000000-0000-0000-0000-000000000000"
            )

    def test_remove_software_from_department(self):
        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        result = departments_service.remove_software_from_department(
            str(self.department.id), str(self.software.id)
        )
        self.assertIsNotNone(result)
        software_list = departments_service.get_software_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(software_list), 0)

    def test_remove_software_from_department_no_link(self):
        result = departments_service.remove_software_from_department(
            str(self.department.id), str(self.software.id)
        )
        self.assertIsNone(result)

    def test_remove_software_from_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.remove_software_from_department(
                "00000000-0000-0000-0000-000000000000", str(self.software.id)
            )
        with self.assertRaises(SoftwareNotFoundException):
            departments_service.remove_software_from_department(
                str(self.department.id), "00000000-0000-0000-0000-000000000000"
            )

    def test_add_hardware_item_to_department(self):
        result = departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        self.assertEqual(
            result["department_id"], str(self.department.id)
        )
        self.assertEqual(
            result["hardware_item_id"], str(self.hardware_item.id)
        )

    def test_add_hardware_item_to_department_idempotent(self):
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        result = departments_service.get_hardware_items_for_department(
            str(self.department.id)
        )
        self.assertEqual(len(result), 1)

    def test_add_hardware_item_to_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.add_hardware_item_to_department(
                "00000000-0000-0000-0000-000000000000", str(self.hardware_item.id)
            )
        with self.assertRaises(HardwareItemNotFoundException):
            departments_service.add_hardware_item_to_department(
                str(self.department.id), "00000000-0000-0000-0000-000000000000"
            )

    def test_remove_hardware_item_from_department(self):
        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        result = departments_service.remove_hardware_item_from_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        self.assertIsNotNone(result)
        hardware_list = (
            departments_service.get_hardware_items_for_department(
                str(self.department.id)
            )
        )
        self.assertEqual(len(hardware_list), 0)

    def test_remove_hardware_item_from_department_no_link(self):
        result = departments_service.remove_hardware_item_from_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        self.assertIsNone(result)

    def test_remove_hardware_item_from_department_not_found(self):
        with self.assertRaises(DepartmentNotFoundException):
            departments_service.remove_hardware_item_from_department(
                "00000000-0000-0000-0000-000000000000", str(self.hardware_item.id)
            )
        with self.assertRaises(HardwareItemNotFoundException):
            departments_service.remove_hardware_item_from_department(
                str(self.department.id), "00000000-0000-0000-0000-000000000000"
            )

    def test_get_all_software_for_departments(self):
        result = departments_service.get_all_software_for_departments()
        self.assertEqual(len(result), 0)

        departments_service.add_software_to_department(
            str(self.department.id), str(self.software.id)
        )
        departments_service.add_software_to_department(
            str(self.department_animation.id), str(self.software_max.id)
        )
        result = departments_service.get_all_software_for_departments()
        self.assertEqual(len(result), 2)
        self.assertIn(self.department.id, result)
        self.assertIn(self.department_animation.id, result)
        self.assertEqual(len(result[self.department.id]), 1)

    def test_get_all_hardware_items_for_departments(self):
        result = (
            departments_service.get_all_hardware_items_for_departments()
        )
        self.assertEqual(len(result), 0)

        departments_service.add_hardware_item_to_department(
            str(self.department.id), str(self.hardware_item.id)
        )
        departments_service.add_hardware_item_to_department(
            str(self.department_animation.id),
            str(self.hardware_item_2.id),
        )
        result = (
            departments_service.get_all_hardware_items_for_departments()
        )
        self.assertEqual(len(result), 2)
        self.assertIn(self.department.id, result)
        self.assertIn(self.department_animation.id, result)
        self.assertEqual(len(result[self.department.id]), 1)
