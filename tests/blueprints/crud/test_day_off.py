from tests.base import ApiDBTestCase

from zou.app.models.time_spent import TimeSpent
from zou.app.services import tasks_service
from zou.app.utils import fields


class DayOffTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.person_id = str(self.user["id"])

    def day_off(self, date, end_date=None, expected_status=201, **data):
        return self.post(
            "data/day-offs",
            {
                "date": date,
                "end_date": end_date or date,
                "person_id": self.person_id,
                **data,
            },
            expected_status,
        )

    def test_get_day_offs(self):
        self.day_off("2024-01-15")
        day_offs = self.get("data/day-offs")
        self.assertEqual(len(day_offs), 1)

    def test_get_day_off(self):
        day_off = self.day_off("2024-01-15")
        day_off_again = self.get(f"data/day-offs/{day_off['id']}")
        self.assertEqual(day_off["id"], day_off_again["id"])
        self.get_404(f"data/day-offs/{fields.gen_uuid()}")

    def test_create_day_off(self):
        day_off = self.day_off("2024-01-15", "2024-01-16")
        self.assertIsNotNone(day_off["id"])
        self.assertEqual(day_off["date"], "2024-01-15")

    def test_update_day_off(self):
        day_off = self.day_off("2024-01-15")
        data = {"description": "Vacation"}
        self.put(f"data/day-offs/{day_off['id']}", data)
        day_off_again = self.get(f"data/day-offs/{day_off['id']}")
        self.assertEqual(data["description"], day_off_again["description"])
        self.put_404(f"data/day-offs/{fields.gen_uuid()}", data)

    def test_delete_day_off(self):
        day_off = self.day_off("2024-01-15")
        self.delete(f"data/day-offs/{day_off['id']}")
        day_offs = self.get("data/day-offs")
        self.assertEqual(day_offs, [])
        self.delete_404(f"data/day-offs/{fields.gen_uuid()}")

    def test_a_day_off_cannot_overlap_another_one(self):
        self.day_off("2024-01-15", "2024-01-18")
        # Touching the first day, the last day, or swallowing the whole
        # period: all of them are the same day counted twice.
        self.day_off("2024-01-10", "2024-01-15", expected_status=400)
        self.day_off("2024-01-18", "2024-01-20", expected_status=400)
        self.day_off("2024-01-01", "2024-01-31", expected_status=400)
        self.day_off("2024-01-19", "2024-01-20")

    def test_a_day_off_does_not_overlap_itself_on_update(self):
        """
        The overlap check runs on update too, and the row being updated is
        excluded from it. Without that, extending a day off would collide
        with the version of itself still stored.
        """
        day_off = self.day_off("2024-01-15", "2024-01-16")
        self.put(
            f"data/day-offs/{day_off['id']}",
            {"date": "2024-01-15", "end_date": "2024-01-18"},
        )
        self.assertEqual(
            self.get(f"data/day-offs/{day_off['id']}")["end_date"],
            "2024-01-18",
        )


class DayOffTimeSpentTestCase(ApiDBTestCase):
    """
    Declaring a day off wipes the hours logged on the days it covers:
    someone cannot have worked on a day they were away.
    """

    def setUp(self):
        super().setUp()
        self.person_id = str(self.user["id"])
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        for day in range(1, 6):
            tasks_service.create_or_update_time_spent(
                str(self.task.id), self.person_id, f"2024-01-0{day}", 100
            )

    def logged_days(self):
        return sorted(
            str(time_spent.date)
            for time_spent in TimeSpent.query.filter_by(
                person_id=self.user["id"]
            ).all()
        )

    def test_a_day_off_of_one_day_wipes_that_day(self):
        self.post(
            "data/day-offs",
            {
                "date": "2024-01-03",
                "end_date": "2024-01-03",
                "person_id": self.person_id,
            },
        )
        self.assertEqual(
            self.logged_days(),
            ["2024-01-01", "2024-01-02", "2024-01-04", "2024-01-05"],
        )

    def test_a_day_off_of_several_days_wipes_all_of_them(self):
        """
        Both bounds have to be read from the column. Written the other way
        round, Python falls back to the reflected operator and the
        interval comes out inverted, which matches nothing as soon as the
        day off lasts more than a day.
        """
        self.post(
            "data/day-offs",
            {
                "date": "2024-01-02",
                "end_date": "2024-01-04",
                "person_id": self.person_id,
            },
        )
        self.assertEqual(self.logged_days(), ["2024-01-01", "2024-01-05"])

    def test_moving_a_day_off_wipes_the_days_it_lands_on(self):
        day_off = self.post(
            "data/day-offs",
            {
                "date": "2024-01-04",
                "end_date": "2024-01-04",
                "person_id": self.person_id,
            },
        )
        self.put(
            f"data/day-offs/{day_off['id']}",
            {"date": "2024-01-01", "end_date": "2024-01-02"},
        )
        self.assertEqual(self.logged_days(), ["2024-01-03", "2024-01-05"])
