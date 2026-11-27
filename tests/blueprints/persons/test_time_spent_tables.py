from tests.base import ApiDBTestCase
from zou.app.services import (
    time_spents_service,
)


class PersonTimeSpentTablesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_task()

    def create_time_spents(self):
        self.person_id = str(self.person.id)
        self.user_id = self.user["id"]

        task_id = str(self.task.id)
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        shot_task_id = str(self.shot_task.id)

        time_spents_service.create_or_update_time_spent(
            task_id, self.person_id, "2018-06-04", 500
        )
        time_spents_service.create_or_update_time_spent(
            shot_task_id, self.person_id, "2018-06-04", 300
        )
        time_spents_service.create_or_update_time_spent(
            task_id, self.person_id, "2018-06-03", 600
        )
        time_spents_service.create_or_update_time_spent(
            task_id, self.person_id, "2018-05-03", 600
        )
        time_spents_service.create_or_update_time_spent(
            task_id, self.person_id, "2018-05-03", 600
        )
        time_spents_service.create_or_update_time_spent(
            task_id, self.user_id, "2018-06-03", 600
        )

    def test_get_month_table(self):
        self.create_time_spents()
        month_table = self.get("/data/persons/time-spents/month-table/2018")
        self.assertEqual(month_table["6"][self.person_id], 1400)
        self.assertEqual(month_table["6"][self.user_id], 600)
        self.assertNotIn("1", month_table)

    def test_get_day_table(self):
        self.create_time_spents()
        day_table = self.get("/data/persons/time-spents/day-table/2018/06")
        self.assertEqual(day_table["3"][self.person_id], 600)
        self.assertEqual(day_table["4"][self.person_id], 800)
        self.assertEqual(day_table["3"][self.user_id], 600)
        self.assertNotIn("1", day_table)

    def test_get_week_table(self):
        self.create_time_spents()
        week_table = self.get("/data/persons/time-spents/week-table/2018")
        self.assertEqual(week_table["18"][self.person_id], 600)
        self.assertEqual(week_table["22"][self.person_id], 600)
        self.assertEqual(week_table["22"][self.user_id], 600)
        self.assertEqual(week_table["23"][self.person_id], 800)
        self.assertNotIn("1", week_table)

    def test_get_time_spents_by_granularity(self):
        """
        The same 600 seconds on the Tree task, reached through the three
        granularities. May 3rd 2018 is in week 18.
        """
        self.create_time_spents()
        for granularity, period in [
            ("month", "2018/5"),
            ("week", "2018/18"),
            ("day", "2018/5/3"),
        ]:
            with self.subTest(granularity=granularity):
                tasks = self.get(
                    f"/data/persons/{self.person_id}"
                    f"/time-spents/{granularity}/{period}"
                )
                self.assertEqual(len(tasks), 1)
                self.assertEqual(tasks[0]["entity_name"], "Tree")
                self.assertEqual(tasks[0]["duration"], 600)
