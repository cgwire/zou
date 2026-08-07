import datetime
import unittest

import pytest

from zou.app.utils import date_helpers
from zou.app.services.exception import WrongDateFormatException


class DateHelpersTestCase(unittest.TestCase):
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
