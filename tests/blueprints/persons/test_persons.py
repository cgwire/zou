import urllib.parse

from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.models.day_off import DayOff
from zou.app.models.person import Person
from zou.app.stores import auth_tokens_store
from zou.app.services import tasks_service
from zou.app.utils import auth, fields


class PersonRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()
        self.generate_fixture_task()
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

    def test_get_persons_filtered_by_choice_field(self):
        # Filtering on a ChoiceType column (role) used to 500: its SQLAlchemy
        # type raises NotImplementedError for python_type.
        persons = self.get("data/persons?role=admin")
        self.assertGreaterEqual(len(persons), 1)
        self.assertTrue(all(p["role"] == "admin" for p in persons))

    # --- Time spents ---

    def test_get_person_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}/time-spents"
            f"?start_date=2024-06-01&end_date=2024-06-30"
        )
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

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
        self.assertGreater(len(result), 0)

    def test_get_person_day_time_spents(self):
        result = self.get(
            f"/data/persons/{self.person_id}" f"/time-spents/day/2024/06/04"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    # --- Time spent tables ---

    def test_the_time_spent_tables_total_by_period(self):
        """
        The eight hundred minutes of setUp read at four granularities, each
        keyed by its period and then by the person who logged them. The two
        tasks they were split across are summed.
        """
        tables = {
            "year": ("/data/persons/time-spents/year-table/", "2024"),
            "month": ("/data/persons/time-spents/month-table/2024", "6"),
            "week": ("/data/persons/time-spents/week-table/2024", "23"),
            "day": ("/data/persons/time-spents/day-table/2024/06", "4"),
        }
        for granularity, (path, period) in tables.items():
            with self.subTest(granularity=granularity):
                self.assertEqual(
                    self.get(path), {period: {self.person_id: 800.0}}
                )

    # --- Day offs ---

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

    def test_get_person_day_off_for_date_is_admin_or_self(self):
        # Leave is between the person and the admins, like the week, month
        # and year routes and like the day off CRUD. A team calendar goes
        # through /data/projects/<id>/day-offs, which scopes to the
        # production and hands the detail to its managers only.
        DayOff.create(
            date="2024-06-10",
            end_date="2024-06-10",
            person_id=self.person.id,
        )
        path = f"/data/persons/{self.person_id}/day-offs/2024-06-10"

        self.generate_fixture_user_supervisor()
        self.log_in_supervisor()
        self.get(path, 403)

        self.log_in_admin()
        self.assertIsNotNone(self.get(path))

    def test_the_day_off_listings_each_hold_their_own_period(self):
        """
        One day off, read back through every window that contains it and
        every neighbouring window that must not. Without the second half a
        listing that ignores its date range passes just as well.
        """
        DayOff.create(
            date="2024-06-12",
            end_date="2024-06-12",
            person_id=self.person.id,
        )
        base = f"/data/persons/{self.person_id}/day-offs"
        # 2024-06-12 is a Wednesday, in ISO week 24. Away from the edges of
        # its week, month and year on purpose: the listings take their end
        # date inclusively while the intervals end on the first day of the
        # next period, so a day off on a boundary shows up in both.
        holds = {
            "every one of theirs": base,
            "its week": f"{base}/week/2024/24",
            "its month": f"{base}/month/2024/06",
            "its year": f"{base}/year/2024",
            "the studio wide month": "/data/persons/day-offs/2024/06",
        }
        misses = {
            "the week before": f"{base}/week/2024/23",
            "the month before": f"{base}/month/2024/05",
            "the year before": f"{base}/year/2023",
            "the studio wide month before": "/data/persons/day-offs/2024/05",
        }
        for period, path in holds.items():
            with self.subTest(holds=period):
                result = self.get(path)
                self.assertEqual(len(result), 1)
                self.assertTrue(result[0]["date"].startswith("2024-06-12"))
        for period, path in misses.items():
            with self.subTest(misses=period):
                self.assertEqual(self.get(path), [])

    # --- Quota shots ---

    def test_the_quota_shot_listings_each_hold_their_own_period(self):
        """
        The shots that counted towards a quota in a period, read through the
        month, week and day the shot belongs to, then through neighbouring
        periods that must not carry it.
        """
        self.shot.update({"nb_frames": 100})
        tasks_service.assign_task(str(self.shot_task.id), self.person_id)
        self.shot_task.update(
            {"end_date": fields.get_date_object("2024-06-04")}
        )

        # The listing is scoped to a production and a task type: without
        # both the query filters on a null project and finds nothing.
        scope = (
            f"?project_id={self.shot_task.project_id}"
            f"&task_type_id={self.shot_task.task_type_id}"
        )
        base = f"/data/persons/{self.person_id}/quota-shots"
        # 2024-06-04 is a Tuesday, in ISO week 23.
        holds = {
            "its month": f"{base}/month/2024/06{scope}",
            "its week": f"{base}/week/2024/23{scope}",
            "its day": f"{base}/day/2024/06/04{scope}",
        }
        misses = {
            "the month before": f"{base}/month/2024/05{scope}",
            "the week before": f"{base}/week/2024/22{scope}",
            "the day before": f"{base}/day/2024/06/03{scope}",
        }
        for period, path in holds.items():
            with self.subTest(holds=period):
                self.assertEqual(
                    [shot["id"] for shot in self.get(path)],
                    [str(self.shot.id)],
                )
        for period, path in misses.items():
            with self.subTest(misses=period):
                self.assertEqual(self.get(path), [])

    # --- Actions ---

    def test_change_password(self):
        result = self.post(
            f"/actions/persons/{self.person_id}/change-password",
            {"password": "newpassword123", "password_2": "newpassword123"},
            200,
        )
        self.assertTrue(result.get("success"))

    def test_change_password_for_new_admin(self):
        new_admin = self.another_admin()
        result = self.post(
            f"/actions/persons/{new_admin.id}/change-password",
            {"password": "newpassword123", "password_2": "newpassword123"},
            200,
        )
        self.assertTrue(result.get("success"))

    def another_admin(self, **overrides):
        """
        A second admin. Whether they carry a password is what separates the
        routes that refuse from the routes that allow: an admin who has
        never set one has nothing to steal.
        """
        return Person.create(
            first_name="Other",
            last_name="Admin",
            role="admin",
            email="other.admin@gmail.com",
            **overrides,
        )

    def assert_the_route_refuses_another_admin(self, action, data):
        """
        Neither password route lets an admin reach into another admin's
        account, and both say so rather than failing silently.
        """
        other_admin = self.another_admin(
            password=auth.encrypt_password("existingpassword")
        )

        result = self.post(
            f"/actions/persons/{other_admin.id}/{action}", data, 400
        )

        self.assertEqual(
            result.get("message"),
            "An admin can't change another admin's password.",
        )

    def test_change_password_for_existing_admin_is_blocked(self):
        self.assert_the_route_refuses_another_admin(
            "change-password",
            {"password": "newpassword123", "password_2": "newpassword123"},
        )

    def test_get_reset_password_link(self):
        email = self.person.email
        result = self.post(
            f"/actions/persons/{self.person_id}/reset-password-link",
            {},
            200,
        )
        reset_link = result["reset_password_link"]
        self.assertIn("/reset-change-password?", reset_link)

        query = urllib.parse.urlparse(reset_link).query
        params = dict(urllib.parse.parse_qsl(query))
        self.assertEqual(params["email"], email)
        # The link carries the very token stored for the reset flow, so it
        # can be used to set a new password just like the emailed link.
        self.assertEqual(
            params["token"], auth_tokens_store.get(f"reset-token-{email}")
        )
        new_password = "newpassword123"
        self.put(
            "auth/reset-password",
            {
                "email": email,
                "token": params["token"],
                "password": new_password,
                "password2": new_password,
            },
            200,
        )
        self.post(
            "auth/login", {"email": email, "password": new_password}, 200
        )

    def test_get_reset_password_link_is_reused(self):
        path = f"/actions/persons/{self.person_id}/reset-password-link"
        first = self.post(path, {}, 200)["reset_password_link"]
        second = self.post(path, {}, 200)["reset_password_link"]
        # A pending token is reused so a previously shared link stays valid.
        self.assertEqual(first, second)

    def test_get_reset_password_link_for_new_admin(self):
        new_admin = self.another_admin()
        result = self.post(
            f"/actions/persons/{new_admin.id}/reset-password-link",
            {},
            200,
        )
        self.assertIn("reset_password_link", result)

    def test_get_reset_password_link_for_existing_admin_is_blocked(self):
        self.assert_the_route_refuses_another_admin("reset-password-link", {})

    def test_clear_avatar(self):
        self.delete(f"/actions/persons/{self.person_id}/clear-avatar")
        person = self.get(f"/data/persons/{self.person_id}")
        self.assertFalse(person.get("has_avatar", False))

    def test_disable_two_factor_authentication(self):
        self.delete(
            f"/actions/persons/{self.person_id}"
            f"/disable-two-factor-authentication",
            400,
        )
        person = self.get(f"/data/persons/{self.person_id}")
        self.assertFalse(person.get("totp_enabled", False))

    def test_invite_person(self):
        """
        The invitation mail. Only an admin sends one, and never to a bot:
        a bot has no mailbox and no password to set.
        """
        path = f"/actions/persons/{self.person.id}/invite"
        with mock.patch("zou.app.utils.emails.send_email") as send_email:
            result = self.get(path)
        self.assertEqual(result, {"success": True, "message": "Email sent"})
        self.assertEqual(send_email.call_count, 1)

        bot = Person.create(
            first_name="Bot",
            last_name="Helper",
            email="bot@example.com",
            is_bot=True,
        )
        self.get(f"/actions/persons/{bot.id}/invite", 403)

        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.get(path, 403)
