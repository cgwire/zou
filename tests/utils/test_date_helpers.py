import datetime
import unittest

import pytest
from freezegun import freeze_time

from zou.app.exceptions import WrongDateFormatException
from zou.app.utils import date_helpers


class DateHelpersTestCase(unittest.TestCase):
    def test_today_follows_the_timezone_from_the_current_instant(self):
        # Built from a bare date, "today" was midnight UTC converted, hence
        # always the previous day west of UTC.
        with freeze_time("2026-09-23T02:00:00"):
            self.assertEqual(
                date_helpers.get_today_string_with_timezone(
                    "America/Los_Angeles"
                ),
                "2026-09-22",
            )
            self.assertEqual(
                date_helpers.get_today_string_with_timezone("Europe/Paris"),
                "2026-09-23",
            )
        with freeze_time("2026-09-23T12:00:00"):
            self.assertEqual(
                date_helpers.get_today_string_with_timezone(
                    "America/Los_Angeles"
                ),
                "2026-09-23",
            )

    def test_date(self):
        date_string = date_helpers.get_date_string_with_timezone(
            "2021-02-10T12:00:00", "Europe/Paris"
        )
        self.assertEqual(date_string, "2021-02-10T13:00:00")

        date_string = date_helpers.get_simple_string_with_timezone_from_date(
            datetime.datetime(2021, 2, 10, 23, 30, 0), "Europe/Paris"
        )
        self.assertEqual(date_string, "2021-02-11")

        date_obj = date_helpers.get_date_from_string("2021-02-10")
        self.assertEqual(date_obj.strftime("%Y-%m-%d"), "2021-02-10")

        start, end = date_helpers.get_year_interval(2021)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-01-01")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2022-01-01")

        start, end = date_helpers.get_month_interval(2021, 2)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-02-01")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-03-01")

        start, end = date_helpers.get_week_interval(2021, 30)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-07-26")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-08-02")

        start, end = date_helpers.get_day_interval(2021, 2, 10)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-02-10")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-02-11")

    def test_timezoned_interval_converts_local_time_to_utc(self):
        """
        The interval bounds come in as local wall-clock time and must come
        out as the UTC instants they name: a Kuala Lumpur day starts at
        16:00 UTC the day before, not at 08:00 UTC the same day.
        """
        start, end = date_helpers.get_timezoned_interval(
            datetime.datetime(2024, 12, 17),
            datetime.datetime(2024, 12, 18),
            "Asia/Kuala_Lumpur",
        )
        self.assertEqual(start, datetime.datetime(2024, 12, 16, 16, 0))
        self.assertEqual(end, datetime.datetime(2024, 12, 17, 16, 0))

        # Plain dates (the week interval helper returns them) are taken as
        # local midnight.
        start, end = date_helpers.get_timezoned_interval(
            datetime.date(2024, 12, 17),
            datetime.date(2024, 12, 18),
            "America/New_York",
        )
        self.assertEqual(start, datetime.datetime(2024, 12, 17, 5, 0))
        self.assertEqual(end, datetime.datetime(2024, 12, 18, 5, 0))

    def test_a_local_day_starts_at_its_first_midnight(self):
        """
        In Havana, clocks go back from 01:00 to 00:00 on 1 November 2026:
        the day starts at the first midnight, 04:00 UTC, an hour before
        the second one. On 8 March they go forward from 00:00 to 01:00:
        the day starts at 01:00, 05:00 UTC.
        """
        self.assertEqual(
            date_helpers.get_utc_from_local_datetime(
                datetime.date(2026, 11, 1), "America/Havana"
            ),
            datetime.datetime(2026, 11, 1, 4, 0),
        )
        self.assertEqual(
            date_helpers.get_utc_from_local_datetime(
                datetime.date(2026, 3, 8), "America/Havana"
            ),
            datetime.datetime(2026, 3, 8, 5, 0),
        )

    def test_a_local_time_met_twice_is_taken_at_its_first_pass(self):
        """
        Dublin keeps its winter time as negative DST: when clocks go back
        from 02:00 to 01:00 on 25 October 2026, 01:30 first comes at 00:30
        UTC, an hour before it comes again.
        """
        self.assertEqual(
            date_helpers.get_utc_from_local_datetime(
                datetime.datetime(2026, 10, 25, 1, 30), "Europe/Dublin"
            ),
            datetime.datetime(2026, 10, 25, 0, 30),
        )

    def test_interval_allows_future_years(self):
        next_year = date_helpers.get_utc_now_datetime().year + 1
        start, _ = date_helpers.get_month_interval(next_year, 1)
        self.assertEqual(start.year, next_year)
        start, _ = date_helpers.get_month_interval(2500, 12)
        self.assertEqual(start.year, 2500)

        with pytest.raises(WrongDateFormatException):
            date_helpers.get_month_interval(2026, 13)
        with pytest.raises(WrongDateFormatException):
            date_helpers.get_day_interval(2026, 2, 30)
        with pytest.raises(WrongDateFormatException):
            date_helpers.get_week_interval(2026, 60)
        with pytest.raises(WrongDateFormatException):
            date_helpers.get_month_interval("abc", 1)
