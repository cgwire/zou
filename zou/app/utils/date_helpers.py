from datetime import date, timedelta


def get_date_from_now(nb_days):
    return date.today() - timedelta(days=nb_days)


def get_date_diff(date_a, date_b):
    return abs((date_b - date_a).total_seconds())
