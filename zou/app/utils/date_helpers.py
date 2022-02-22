import isoweek

from babel.dates import format_datetime
from datetime import date, datetime, timedelta
from dateutil import relativedelta
from zou.app.services.exception import WrongDateFormatException


def get_now():
    return get_string_with_timezone_from_date(datetime.now(), "UTC")


def get_date_from_now(nb_days):
    return date.today() - timedelta(days=nb_days)


def get_date_diff(date_a, date_b):
    return abs((date_b - date_a).total_seconds())


def get_date_string_with_timezone(date_string, timezone):
    """
    Apply given timezone to given date and return it as a string.
    """
    date_obj = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")
    return format_datetime(date_obj, "yyyy-MM-ddTHH:mm:ss", tzinfo=timezone)


def get_string_with_timezone_from_date(date_obj, timezone):
    """
    Apply given timezone to given date and return it as a string.
    """
    return format_datetime(date_obj, "yyyy-MM-ddTHH:mm:ss", tzinfo=timezone)


def get_simple_string_with_timezone_from_date(date_obj, timezone):
    """
    Apply given timezone to given date and return it as a string (only date).
    """
    return format_datetime(date_obj, "yyyy-MM-dd", tzinfo=timezone)


def get_today_string_with_timezone(timezone):
    """
    Get today date in string format with timezone applied.
    """
    return get_simple_string_with_timezone_from_date(date.today(), timezone)


def get_date_from_string(date_str):
    """
    Parse a date string and returns a date object.
    """
    return datetime.strptime(date_str, "%Y-%m-%d")


def get_datetime_from_string(date_str):
    """
    Parse a datetime string and returns a datetime object.
    """
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")


def get_year_interval(year):
    """
    Get a tuple containing start date and end date for given year.
    """
    year = int(year)
    if year > datetime.now().year or year < 2010:
        raise WrongDateFormatException

    start = datetime(year, 1, 1)
    end = start + relativedelta.relativedelta(years=1)
    return start, end


def get_month_interval(year, month):
    """
    Get a tuple containing start date and end date for given year and month.
    """
    year = int(year)
    month = int(month)
    if year > datetime.now().year or year < 2010 or month < 1 or month > 12:
        raise WrongDateFormatException

    start = datetime(year, month, 1)
    end = start + relativedelta.relativedelta(months=1)
    return start, end


def get_week_interval(year, week):
    """
    Get a tuple containing start date and end date for given year and week.
    """
    year = int(year)
    week = int(week)
    if year > datetime.now().year or year < 2010 or week < 1 or week > 52:
        raise WrongDateFormatException
    start = isoweek.Week(year, week).monday()
    end = start + relativedelta.relativedelta(days=7)
    return start, end


def get_day_interval(year, month, day):
    """
    Get a tuple containing start date and end date for given day.
    """
    year = int(year)
    month = int(month)
    day = int(day)
    if (
        year > datetime.now().year
        or year < 2010
        or month < 1
        or month > 12
        or day < 1
        or day > 31
    ):
        raise WrongDateFormatException
    start = datetime(year, month, day)
    end = start + relativedelta.relativedelta(days=1)
    return start, end


def get_timezoned_interval(start, end, timezone):
    """
    Get interval between two dates based on timezones.
    """
    return (
        get_string_with_timezone_from_date(start, timezone),
        get_string_with_timezone_from_date(end, timezone),
    )


def get_business_days(start, end):
    """
    Returns the number of business days between two dates.
    """
    daygenerator = (
        start + timedelta(x + 1) for x in range((end - start).days)
    )
    return sum(1 for day in daygenerator if day.weekday() < 5)


def add_business_days_to_date(date, nb_days):
    while nb_days > 0:
        date += timedelta(days=1)
        if date.weekday() < 5:
            nb_days -= 1
    return date
