import datetime
import random

from tests.base import ApiDBTestCase

from zou.app.models.time_spent import TimeSpent

from zou.app.utils import fields


class TimeSpentTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_task()
        # Distinct deterministic dates: (person, task, date) is unique, so
        # letting mixer draw random dates makes the test flaky on collision.
        dates = iter(datetime.date(2024, 1, day) for day in [1, 2, 3])
        self.tasks = self.generate_data(
            TimeSpent,
            3,
            task_id=self.task.id,
            person_id=self.person.id,
            date=lambda: next(dates),
            duration=lambda: random.uniform(0.1, 10000),
        )

    def test_get_time_spents(self):
        time_spents = self.get("data/time-spents")
        self.assertEqual(len(time_spents), 3)
        self.assertEqual(time_spents[0]["type"], "TimeSpent")

    def test_get_time_spent(self):
        time_spent = self.get_first("data/time-spents")
        time_spent_again = self.get(f"data/time-spents/{time_spent['id']}")
        self.assertEqual(time_spent, time_spent_again)
        self.get_404(f"data/time-spents/{fields.gen_uuid()}")

    def test_create_time_spent(self):
        data = {
            "person_id": self.person.id,
            "task_id": self.task.id,
            "date": "2017-09-23",
            "duration": 3600,
        }
        self.time_spent = self.post("data/time-spents", data)
        self.assertIsNotNone(self.time_spent["id"])

        time_spents = self.get("data/time-spents")
        self.assertEqual(len(time_spents), 4)

        time_spents = self.get(f"data/time-spents?person_id={self.person.id}")
        self.assertEqual(len(time_spents), 4)

    def test_update_time_spent(self):
        time_spent = self.get_first("data/time-spents")
        data = {"duration": 7200}
        self.put(f"data/time-spents/{time_spent['id']}", data)
        time_spent_again = self.get(f"data/time-spents/{time_spent['id']}")
        self.assertEqual(data["duration"], time_spent_again["duration"])
        self.put_404(f"data/time-spents/{fields.gen_uuid()}", data)

    def test_delete_time_spent(self):
        time_spents = self.get("data/time-spents")
        self.assertEqual(len(time_spents), 3)

        time_spent = time_spents[0]
        self.delete(f"data/time-spents/{time_spent['id']}")

        time_spents = self.get("data/time-spents")
        self.assertEqual(len(time_spents), 2)
        self.delete_404(f"data/time-spents/{fields.gen_uuid()}")

    def test_filter_by_date_range(self):
        # The three fixtures sit on January 1st, 2nd and 3rd.
        time_spents = self.get(
            "data/time-spents?start_date=2024-01-01&end_date=2024-01-02"
        )
        self.assertEqual(len(time_spents), 2)
        self.assertEqual(
            {ts["date"] for ts in time_spents}, {"2024-01-01", "2024-01-02"}
        )
        time_spents = self.get(
            "data/time-spents?start_date=2024-02-01&end_date=2024-02-28"
        )
        self.assertEqual(time_spents, [])

    def test_date_range_needs_both_bounds(self):
        self.get("data/time-spents?start_date=2024-01-01", 400)
        self.get("data/time-spents?end_date=2024-01-01", 400)
