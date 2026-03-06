from tests.base import ApiDBTestCase

from zou.app.models.day_off import DayOff


class PersonRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonRoutesTestCase, self).setUp()
        self.generate_fixture_person()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        self.person_id = str(self.person.id)
        task_id = str(self.task.id)
        shot_task_id = str(self.shot_task.id)

        self.post(
            f"/actions/tasks/{task_id}/time-spents"
            f"/2024-06-04/persons/{self.person_id}",
            {"duration": 500},
        )
        self.post(
            f"/actions/tasks/{shot_task_id}/time-spents"
            f"/2024-06-04/persons/{self.person_id}",
            {"duration": 300},
        )

    # --- Time spents ---

    def test_get_person_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}/time-spents"
            f"?start_date=2024-06-01&end_date=2024-06-30"
        )
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_get_person_year_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}/time-spents/year/2024"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        durations = [r["duration"] for r in result]
        self.assertIn(500.0, durations)
        self.assertIn(300.0, durations)

    def test_get_person_month_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}/time-spents/month/2024/06"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_get_person_week_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}/time-spents/week/2024/23"
        )
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)

    def test_get_person_day_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}"
            f"/time-spents/day/2024/06/04"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    # --- Time spent tables ---

    def test_get_time_spents_year_table(self):
        result = self.get("/data/persons/time-spents/year-table/")
        self.assertIsInstance(result, dict)

    def test_get_time_spents_month_table(self):
        result = self.get(
            "/data/persons/time-spents/month-table/2024"
        )
        self.assertIsInstance(result, dict)

    def test_get_time_spents_week_table(self):
        result = self.get(
            "/data/persons/time-spents/week-table/2024"
        )
        self.assertIsInstance(result, dict)

    def test_get_time_spents_day_table(self):
        result = self.get(
            "/data/persons/time-spents/day-table/2024/06"
        )
        self.assertIsInstance(result, dict)

    # --- Day offs ---

    def test_get_person_day_offs(self):
        result = self.get(
            f"/data/persons/{self.person_id}/day-offs"
        )
        self.assertIsInstance(result, list)

    def test_get_person_day_off_for_date(self):
        DayOff.create(
            date="2024-06-10",
            end_date="2024-06-10",
            person_id=self.person.id,
        )
        result = self.get(
            f"/data/persons/{self.person_id}/day-offs/2024-06-10"
        )
        self.assertIsNotNone(result)

    def test_get_person_day_offs_week(self):
        result = self.get(
            f"/data/persons/{self.person_id}/day-offs/week/2024/23"
        )
        self.assertIsInstance(result, list)

    def test_get_person_day_offs_month(self):
        result = self.get(
            f"/data/persons/{self.person_id}/day-offs/month/2024/06"
        )
        self.assertIsInstance(result, list)

    def test_get_person_day_offs_year(self):
        result = self.get(
            f"/data/persons/{self.person_id}/day-offs/year/2024"
        )
        self.assertIsInstance(result, list)

    def test_get_day_offs_for_month(self):
        result = self.get("/data/persons/day-offs/2024/06")
        self.assertIsInstance(result, list)

    # --- Quota shots ---

    def test_get_person_quota_shots_month(self):
        result = self.get(
            f"/data/persons/{self.person_id}"
            f"/quota-shots/month/2024/06"
        )
        self.assertIsInstance(result, list)

    def test_get_person_quota_shots_week(self):
        result = self.get(
            f"/data/persons/{self.person_id}"
            f"/quota-shots/week/2024/23"
        )
        self.assertIsInstance(result, list)

    def test_get_person_quota_shots_day(self):
        result = self.get(
            f"/data/persons/{self.person_id}"
            f"/quota-shots/day/2024/06/04"
        )
        self.assertIsInstance(result, list)

    # --- Actions ---

    def test_change_password(self):
        result = self.post(
            f"/actions/persons/{self.person_id}/change-password",
            {"password": "newpassword123", "password_2": "newpassword123"},
            200,
        )
        self.assertTrue(result.get("success"))

    def test_clear_avatar(self):
        self.delete(
            f"/actions/persons/{self.person_id}/clear-avatar"
        )
        person = self.get(f"/data/persons/{self.person_id}")
        self.assertFalse(person.get("has_avatar", False))

    def test_disable_two_factor_authentication(self):
        result = self.delete(
            f"/actions/persons/{self.person_id}"
            f"/disable-two-factor-authentication",
            400,
        )
        person = self.get(f"/data/persons/{self.person_id}")
        self.assertFalse(person.get("totp_enabled", False))
