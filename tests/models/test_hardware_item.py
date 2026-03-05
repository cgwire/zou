from tests.base import ApiDBTestCase
from zou.app.models.hardware_item import HardwareItem
from zou.app.utils import fields


class HardwareItemTestCase(ApiDBTestCase):
    def setUp(self):
        super(HardwareItemTestCase, self).setUp()
        self.generate_data(HardwareItem, 3)

    def test_get_hardware_items(self):
        hardware_items = self.get("data/hardware-items")
        self.assertEqual(len(hardware_items), 3)

    def test_get_hardware_item(self):
        hardware_item = self.get_first("data/hardware-items")
        hardware_item_again = self.get(
            "data/hardware-items/%s" % hardware_item["id"]
        )
        self.assertEqual(hardware_item, hardware_item_again)
        self.get_404("data/hardware-items/%s" % fields.gen_uuid())

    def test_create_hardware_item(self):
        data = {"name": "Workstation 01", "short_name": "WS01"}
        self.hardware_item = self.post("data/hardware-items", data)
        self.assertIsNotNone(self.hardware_item["id"])
        hardware_items = self.get("data/hardware-items")
        self.assertEqual(len(hardware_items), 4)

    def test_update_hardware_item(self):
        hardware_item = self.get_first("data/hardware-items")
        data = {"monthly_cost": 500}
        self.put("data/hardware-items/%s" % hardware_item["id"], data)
        hardware_item_again = self.get(
            "data/hardware-items/%s" % hardware_item["id"]
        )
        self.assertEqual(data["monthly_cost"], hardware_item_again["monthly_cost"])
        self.put_404("data/hardware-items/%s" % fields.gen_uuid(), data)

    def test_delete_hardware_item(self):
        hardware_items = self.get("data/hardware-items")
        self.assertEqual(len(hardware_items), 3)
        hardware_item = hardware_items[0]
        self.delete("data/hardware-items/%s" % hardware_item["id"])
        hardware_items = self.get("data/hardware-items")
        self.assertEqual(len(hardware_items), 2)
        self.delete_404("data/hardware-items/%s" % fields.gen_uuid())
