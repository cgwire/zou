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
