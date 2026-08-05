from tests.base import ApiDBTestCase
from zou.app.utils import fields


class DayOffTestCase(ApiDBTestCase):
    def setUp(self):
        super(DayOffTestCase, self).setUp()
        self.person_id = str(self.user["id"])

    def test_get_day_offs(self):
        self.post(
            "data/day-offs",
            {
                "date": "2024-01-15",
                "end_date": "2024-01-15",
                "person_id": self.person_id,
            },
        )
        day_offs = self.get("data/day-offs")
        self.assertEqual(len(day_offs), 1)

    def test_get_day_off(self):
        day_off = self.post(
            "data/day-offs",
            {
                "date": "2024-01-15",
                "end_date": "2024-01-15",
                "person_id": self.person_id,
            },
        )
        day_off_again = self.get(f"data/day-offs/{day_off['id']}")
        self.assertEqual(day_off["id"], day_off_again["id"])
        self.get_404(f"data/day-offs/{fields.gen_uuid()}")

    def test_create_day_off(self):
        data = {
            "date": "2024-01-15",
            "end_date": "2024-01-16",
            "person_id": self.person_id,
        }
        day_off = self.post("data/day-offs", data)
        self.assertIsNotNone(day_off["id"])
        self.assertEqual(day_off["date"], "2024-01-15")

    def test_update_day_off(self):
        day_off = self.post(
            "data/day-offs",
            {
                "date": "2024-01-15",
                "end_date": "2024-01-15",
                "person_id": self.person_id,
            },
        )
        data = {"description": "Vacation"}
        self.put(f"data/day-offs/{day_off['id']}", data)
        day_off_again = self.get(f"data/day-offs/{day_off['id']}")
        self.assertEqual(data["description"], day_off_again["description"])
        self.put_404(f"data/day-offs/{fields.gen_uuid()}", data)

    def test_delete_day_off(self):
        day_off = self.post(
            "data/day-offs",
            {
                "date": "2024-01-15",
                "end_date": "2024-01-15",
                "person_id": self.person_id,
            },
        )
        self.delete(f"data/day-offs/{day_off['id']}")
        day_offs = self.get("data/day-offs")
        self.assertEqual(len(day_offs), 0)
        self.delete_404(f"data/day-offs/{fields.gen_uuid()}")
