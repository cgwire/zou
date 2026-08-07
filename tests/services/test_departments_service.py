from tests.base import ApiDBTestCase

from zou.app.models.hardware_item import HardwareItem
from zou.app.services.exception import (
    DepartmentNotFoundException,
    SoftwareNotFoundException,
    HardwareItemNotFoundException,
)

from zou.app.services import departments_service

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class DepartmentLinksMixin:
    """
    Software and hardware hang off departments through two mirrored sets of
    functions built on one grouping helper, so they share one story here and
    differ only in what each subclass points at.

    Not a TestCase, so neither loader collects it on its own.
    """

    item_key = None
    item_not_found = None

    def setUp(self):
        super().setUp()

        self.generate_fixture_department()
        self.generate_fixture_software()
        self.hardware_item = HardwareItem.create(
            name="Wacom Tablet", short_name="wacom"
        )
        self.hardware_item_2 = HardwareItem.create(
            name="GPU RTX", short_name="gpu"
        )
        self.department_id = str(self.department.id)
        self.other_department_id = str(self.department_animation.id)
        first, second = self.items()
        self.item_id = str(first.id)
        self.other_item_id = str(second.id)
        self.item_name = first.name

    def items(self):
        raise NotImplementedError

    def test_the_listing_starts_empty_and_holds_what_is_added(self):
        self.assertEqual(self.listing(self.department_id), [])

        self.add(self.department_id, self.item_id)

        result = self.listing(self.department_id)
        self.assertEqual([held["name"] for held in result], [self.item_name])

    def test_the_listing_is_scoped_to_its_department(self):
        self.add(self.department_id, self.item_id)

        self.assertEqual(self.listing(self.other_department_id), [])

    def test_the_listing_refuses_an_unknown_department(self):
        with self.assertRaises(DepartmentNotFoundException):
            self.listing(UNKNOWN)

    def test_adding_returns_the_link(self):
        result = self.add(self.department_id, self.item_id)

        self.assertEqual(result["department_id"], self.department_id)
        self.assertEqual(result[self.item_key], self.item_id)

    def test_adding_twice_leaves_one_link(self):
        self.add(self.department_id, self.item_id)

        self.add(self.department_id, self.item_id)

        self.assertEqual(len(self.listing(self.department_id)), 1)

    def test_adding_refuses_an_unknown_side(self):
        with self.assertRaises(DepartmentNotFoundException):
            self.add(UNKNOWN, self.item_id)
        with self.assertRaises(self.item_not_found):
            self.add(self.department_id, UNKNOWN)

    def test_removing_takes_the_link_out(self):
        self.add(self.department_id, self.item_id)

        self.assertIsNotNone(self.remove(self.department_id, self.item_id))

        self.assertEqual(self.listing(self.department_id), [])

    def test_removing_what_was_never_linked_is_no_error(self):
        self.assertIsNone(self.remove(self.department_id, self.item_id))

    def test_removing_refuses_an_unknown_side(self):
        with self.assertRaises(DepartmentNotFoundException):
            self.remove(UNKNOWN, self.item_id)
        with self.assertRaises(self.item_not_found):
            self.remove(self.department_id, UNKNOWN)

    def test_the_studio_wide_listing_groups_by_department(self):
        self.assertEqual(self.all_listings(), {})
        self.add(self.department_id, self.item_id)
        self.add(self.other_department_id, self.other_item_id)

        result = self.all_listings()

        # Keyed by the raw department ids the query returns.
        self.assertEqual(
            {
                str(department_id): [held["id"] for held in held_items]
                for department_id, held_items in result.items()
            },
            {
                self.department_id: [self.item_id],
                self.other_department_id: [self.other_item_id],
            },
        )


class DepartmentSoftwareTestCase(DepartmentLinksMixin, ApiDBTestCase):
    item_key = "software_id"
    item_not_found = SoftwareNotFoundException
    add = staticmethod(departments_service.add_software_to_department)
    remove = staticmethod(departments_service.remove_software_from_department)
    listing = staticmethod(departments_service.get_software_for_department)
    all_listings = staticmethod(
        departments_service.get_all_software_for_departments
    )

    def items(self):
        return self.software, self.software_max


class DepartmentHardwareTestCase(DepartmentLinksMixin, ApiDBTestCase):
    item_key = "hardware_item_id"
    item_not_found = HardwareItemNotFoundException
    add = staticmethod(departments_service.add_hardware_item_to_department)
    remove = staticmethod(
        departments_service.remove_hardware_item_from_department
    )
    listing = staticmethod(
        departments_service.get_hardware_items_for_department
    )
    all_listings = staticmethod(
        departments_service.get_all_hardware_items_for_departments
    )

    def items(self):
        return self.hardware_item, self.hardware_item_2
