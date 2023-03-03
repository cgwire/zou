from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    DateTimeSpentsResource,
    DayOffResource,
    DayOffForMonthResource,
    DesktopLoginsResource,
    InvitePersonResource,
    NewPersonResource,
    PersonMonthQuotaShotsResource,
    PersonWeekQuotaShotsResource,
    PersonDayQuotaShotsResource,
    PersonMonthTimeSpentsResource,
    PersonMonthAllTimeSpentsResource,
    PersonWeekTimeSpentsResource,
    PersonDayTimeSpentsResource,
    PersonWeekDayOffResource,
    PersonYearDayOffResource,
    PersonMonthDayOffResource,
    PresenceLogsResource,
    TimeSpentsResource,
    TimeSpentMonthResource,
    TimeSpentMonthsResource,
    TimeSpentWeekResource,
    TimeSpentYearsResource,
    PersonYearTimeSpentsResource,
    AddToDepartmentResource,
    RemoveFromDepartmentResource,
    ChangePasswordForPersonResource,
    DisableTwoFactorAuthenticationPersonResource,
)

routes = [
    ("/data/persons/new", NewPersonResource),
    (
        "/data/persons/<uuid:person_id>/desktop-login-logs",
        DesktopLoginsResource,
    ),
    ("/data/persons/presence-logs/<string:month_date>", PresenceLogsResource),
    ("/data/persons/<uuid:person_id>/time-spents", TimeSpentsResource),
    (
        "/data/persons/<uuid:person_id>/time-spents/<string:date>",
        DateTimeSpentsResource,
    ),
    ("/data/persons/<uuid:person_id>/day-offs/<string:date>", DayOffResource),
    (
        "/data/persons/<uuid:person_id>/time-spents/year/<string:year>",
        PersonYearTimeSpentsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/time-spents/month/<string:year>/<string:month>",
        PersonMonthTimeSpentsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/time-spents/month/all/<string:year>/<string:month>",
        PersonMonthAllTimeSpentsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/time-spents/week/<string:year>/<string:week>",
        PersonWeekTimeSpentsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/time-spents/day/<string:year>/<string:month>/<string:day>",
        PersonDayTimeSpentsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/quota-shots/month/<string:year>/<string:month>",
        PersonMonthQuotaShotsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/quota-shots/week/<string:year>/<string:week>",
        PersonWeekQuotaShotsResource,
    ),
    (
        "/data/persons/<uuid:person_id>/quota-shots/day/<string:year>/<string:month>/<string:day>",
        PersonDayQuotaShotsResource,
    ),
    ("/data/persons/time-spents/year-table/", TimeSpentYearsResource),
    (
        "/data/persons/time-spents/month-table/<string:year>",
        TimeSpentMonthsResource,
    ),
    (
        "/data/persons/time-spents/week-table/<string:year>",
        TimeSpentWeekResource,
    ),
    (
        "/data/persons/time-spents/day-table/<string:year>/<string:month>",
        TimeSpentMonthResource,
    ),
    (
        "/data/persons/day-offs/<string:year>/<string:month>",
        DayOffForMonthResource,
    ),
    (
        "/data/persons/<uuid:person_id>/day-offs/week/<string:year>/<string:week>",
        PersonWeekDayOffResource,
    ),
    (
        "/data/persons/<uuid:person_id>/day-offs/month/<string:year>/<string:month>",
        PersonMonthDayOffResource,
    ),
    (
        "/data/persons/<uuid:person_id>/day-offs/year/<string:year>",
        PersonYearDayOffResource,
    ),
    ("/actions/persons/<uuid:person_id>/invite", InvitePersonResource),
    (
        "/actions/persons/<uuid:person_id>/departments/add",
        AddToDepartmentResource,
    ),
    (
        "/actions/persons/<uuid:person_id>/departments/<uuid:department_id>",
        RemoveFromDepartmentResource,
    ),
    (
        "/actions/persons/<uuid:person_id>/change-password",
        ChangePasswordForPersonResource,
    ),
    (
        "/actions/persons/<uuid:person_id>/disable-two-factor-authentication",
        DisableTwoFactorAuthenticationPersonResource,
    ),
]

blueprint = create_blueprint_for_api("persons", routes)
