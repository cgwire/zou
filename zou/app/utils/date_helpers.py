import datetime

import pytz
from babel.dates import format_datetime
from dateutil import relativedelta

from zou.app.exceptions import WrongDateFormatException


def get_now():
    """
    Return the current UTC time as a "YYYY-MM-DDTHH:MM:SS" string.
    """
    return get_string_with_timezone_from_date(get_utc_now_datetime(), "UTC")


def get_utc_now_datetime():
    """
    Return the current UTC time as a naive datetime.
    """
    return datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)


def get_date_from_now(nb_days):
    """
    Return the date nb_days before today (local date of the server).
    """
    return datetime.date.today() - datetime.timedelta(days=nb_days)


def get_date_diff(date_a, date_b):
    """
    Return the absolute difference between two dates, in seconds (float).
    """
    return abs((date_b - date_a).total_seconds())


def get_date_string(date_obj, milliseconds=False):
    """
    Return the given datetime as an ISO string without timezone. If
    milliseconds is True, include the microseconds.
    """
    if milliseconds:
        return date_obj.strftime("%Y-%m-%dT%H:%M:%S.%f")
    else:
        return date_obj.strftime("%Y-%m-%dT%H:%M:%S")


def get_date_string_with_timezone(date_string, timezone):
    """
    Apply the given timezone to the given date and return it as a string.
    """
    date_obj = datetime.datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")
    return format_datetime(date_obj, "yyyy-MM-ddTHH:mm:ss", tzinfo=timezone)


def get_string_with_timezone_from_date(date_obj, timezone):
    """
    Apply the given timezone to the given date and return it as a string.
    """
    return format_datetime(date_obj, "yyyy-MM-ddTHH:mm:ss", tzinfo=timezone)


def get_simple_string_with_timezone_from_date(date_obj, timezone):
    """
    Apply the given timezone to the given date and return it as a string
    (date only).
    """
    return format_datetime(date_obj, "yyyy-MM-dd", tzinfo=timezone)


def get_today_string_with_timezone(timezone):
    """
    Return the date of today as a string, with the timezone applied.
    """
    # Start from the current instant: a bare date counts as midnight UTC,
    # and goes to the previous day after the conversion west of UTC.
    return get_simple_string_with_timezone_from_date(
        datetime.datetime.now(tz=datetime.timezone.utc), timezone
    )


def get_date_from_string(date_str):
    """
    Parse a "YYYY-MM-DD" string and return a datetime at midnight.
    """
    return datetime.datetime.strptime(date_str, "%Y-%m-%d")


def get_datetime_from_string(date_str, milliseconds=False):
    """
    Parse a datetime string and return a datetime object.
    """
    if milliseconds:
        return datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f")
    else:
        return datetime.datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")


def get_year_interval(year):
    """
    Return a tuple with the start date and the end date of the given year.
    """
    try:
        start = datetime.datetime(int(year), 1, 1)
        end = start + relativedelta.relativedelta(years=1)
    except (ValueError, OverflowError):
        raise WrongDateFormatException
    return start, end


def get_month_interval(year, month):
    """
    Return a tuple with the start date and the end date of the given year
    and month.
    """
    try:
        start = datetime.datetime(int(year), int(month), 1)
        end = start + relativedelta.relativedelta(months=1)
    except (ValueError, OverflowError):
        raise WrongDateFormatException
    return start, end


def get_week_interval(year, week):
    """
    Return a tuple with the start date and the end date of the given year
    and week.
    """
    try:
        start = datetime.date.fromisocalendar(int(year), int(week), 1)
        end = start + relativedelta.relativedelta(days=7)
    except (ValueError, OverflowError):
        raise WrongDateFormatException
    return start, end


def get_day_interval(year, month, day):
    """
    Return a tuple with the start date and the end date of the given day.
    """
    try:
        start = datetime.datetime(int(year), int(month), int(day))
        end = start + relativedelta.relativedelta(days=1)
    except (ValueError, OverflowError):
        raise WrongDateFormatException
    return start, end


def get_timezoned_interval(start, end, timezone):
    """
    Convert an interval in the local time of the given timezone into its
    naive UTC equivalent, for comparison with datetime columns in UTC.
    """
    return (
        get_utc_from_local_datetime(start, timezone),
        get_utc_from_local_datetime(end, timezone),
    )


def get_utc_from_local_datetime(date_obj, timezone):
    """
    Read a naive date or datetime as local time in the given timezone and
    return the matching naive UTC datetime. If a local time occurs two
    times (when clocks go back), use its first occurrence. If a local time
    does not occur (when clocks go forward), use it as if the clocks did
    not change yet. Thus, a local midnight is always the first instant of
    its day.
    """
    if not isinstance(date_obj, datetime.datetime):
        date_obj = datetime.datetime.combine(date_obj, datetime.time.min)
    tz = pytz.timezone(timezone)
    try:
        localized = tz.localize(date_obj, is_dst=None)
    except pytz.AmbiguousTimeError:
        # Use the earlier of the two instants. If winter time is a negative
        # DST, as in Dublin, is_dst alone would select the second one.
        localized = min(
            tz.localize(date_obj, is_dst=True),
            tz.localize(date_obj, is_dst=False),
        )
    except pytz.NonExistentTimeError:
        localized = tz.localize(date_obj, is_dst=False)
    return localized.astimezone(pytz.utc).replace(tzinfo=None)


def add_business_days_to_date(date, nb_days):
    """
    Add a number of business days to a date. Business days are Monday to
    Friday.
    """
    while nb_days > 0:
        date += datetime.timedelta(days=1)
        if date.weekday() < 5:
            nb_days -= 1
    return date
