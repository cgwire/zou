from babel.dates import format_datetime
from datetime import date, datetime, timedelta


def get_date_from_now(nb_days):
    return date.today() - timedelta(days=nb_days)


def get_date_diff(date_a, date_b):
    return abs((date_b - date_a).total_seconds())


def get_date_string_with_timezone(date_string, timezone):
    """
    Apply given timezone to given date and return it as a string.
    """
    date_obj = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")
    return format_datetime(
        date_obj,
        "yyyy-MM-ddTHH:mm:ss",
        tzinfo=timezone
    )


def get_today_string_with_timezone(timezone):
    date_obj = date.today()
    return format_datetime(
        date_obj,
        "yyyy-MM-dd",
        tzinfo=timezone
    )
