import datetime

from flask import abort, request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from babel.dates import format_datetime

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    persons_service,
    tasks_service,
    time_spents_service,
    shots_service,
    user_service,
)
from zou.app.utils import (
    permissions,
    csv_utils,
    auth,
    emails,
    fields,
    date_helpers,
)
from zou.app.services.exception import (
    DepartmentNotFoundException,
    WrongDateFormatException,
    WrongParameterException,
    UnactiveUserException,
    TwoFactorAuthenticationNotEnabledException,
    PersonInProtectedAccounts,
)
from zou.app.services.auth_service import (
    disable_two_factor_authentication_for_person,
)


class DesktopLoginsResource(Resource, ArgsMixin):
    """
    Allow to create and retrieve desktop login logs. Desktop login logs can only
    be created by current user.
    """

    @jwt_required()
    def get(self, person_id):
        """
        Retrieve desktop login logs.
        ---
        tags:
        - Persons
        description: Desktop login logs can only be created by current user.
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Desktop login logs
        """
        current_user = persons_service.get_current_user()
        if (
            current_user["id"] != person_id
            and not permissions.has_manager_permissions()
        ):
            raise permissions.PermissionDenied

        persons_service.get_person(person_id)
        return persons_service.get_desktop_login_logs(person_id)

    @jwt_required()
    def post(self, person_id):
        """
        Create desktop login logs.
        ---
        tags:
        - Persons
        description: Add a new log entry for desktop logins.
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: date
            required: True
            type: string
            format: date
            example: "2022-07-12"
        responses:
            201:
                description: Desktop login log entry created.
        """
        args = self.get_args([("date", date_helpers.get_utc_now_datetime())])

        current_user = persons_service.get_current_user()
        if (
            current_user["id"] != person_id
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied

        desktop_login_log = persons_service.create_desktop_login_logs(
            person_id, args["date"]
        )

        return desktop_login_log, 201


class PresenceLogsResource(Resource):
    """
    Return a csv file containing the presence logs based on a daily basis.
    """

    @jwt_required()
    def get(self, month_date):
        """
        Return a csv file containing the presence logs based on a daily basis.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: month_date
            required: True
            type: string
            format: date
            example: "2022-07"
        responses:
            200:
                description: CSV file containing the presence logs based on a daily basis
        """
        permissions.check_admin_permissions()
        date = datetime.datetime.strptime(month_date, "%Y-%m")
        presence_logs = persons_service.get_presence_logs(
            date.year, date.month
        )
        return csv_utils.build_csv_response(presence_logs)


class TimeSpentsResource(Resource, ArgsMixin):
    """
    Get all time spents for the given person.
    Optionnaly can accept date range parameters.
    """

    @jwt_required()
    def get(self, person_id):
        user_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        if not start_date and not end_date:
            return time_spents_service.get_time_spents(person_id)

        if None in [start_date, end_date]:
            abort(
                400,
                "If querying for a range of dates, both a `start_date` and"
                " an `end_date` must be given.",
            )

        try:
            return time_spents_service.get_time_spents_range(
                person_id, start_date, end_date
            )
        except WrongDateFormatException:
            abort(
                400,
                f"Wrong date format for {start_date} and/or {end_date}",
            )


class DateTimeSpentsResource(Resource):
    """
    Get time spents for given person and date.
    """

    @jwt_required()
    def get(self, person_id, date):
        """
        Get time spents for given person and date.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: True
            type: string
            format: date
            example: "2022-07-12"
        responses:
            200:
                description: Time spents for given person and date
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        department_ids = None
        project_ids = None
        if not permissions.has_admin_permissions():
            if persons_service.get_current_user()["id"] != person_id:
                if (
                    permissions.has_manager_permissions()
                    or permissions.has_supervisor_permissions()
                ):
                    project_ids = [
                        project["id"]
                        for project in user_service.get_projects()
                    ]
                    if permissions.has_supervisor_permissions():
                        department_ids = persons_service.get_current_user(
                            True
                        ).get("departments", [])
                else:
                    raise permissions.PermissionDenied
        try:
            return time_spents_service.get_time_spents(
                person_id,
                date,
                project_ids=project_ids,
                department_ids=department_ids,
            )
        except WrongDateFormatException:
            abort(404)


class DayOffResource(Resource):
    """
    Get day off object for given person and date.
    """

    @jwt_required()
    def get(self, person_id, date):
        """
        Get day off object for given person and date.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: True
            type: string
            format: date
            example: "2022-07-12"
        responses:
            200:
                description: Day off object for given person and date
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        current_user = persons_service.get_current_user()
        if current_user["id"] != person_id:
            try:
                permissions.check_at_least_supervisor_permissions()
            except permissions.PermissionDenied:
                return []
        try:
            return time_spents_service.get_day_off(person_id, date)
        except WrongDateFormatException:
            abort(404)


class PersonDurationTimeSpentsResource(Resource, ArgsMixin):
    """
    Parent class for all person durations time spents resource.
    """

    def get_project_department_arguments(self, person_id):
        project_id = self.get_project_id()
        department_ids = None
        if not permissions.has_admin_permissions():
            if persons_service.get_current_user()["id"] != person_id:
                if (
                    permissions.has_manager_permissions()
                    or permissions.has_supervisor_permissions()
                ):
                    project_ids = [
                        project["id"]
                        for project in user_service.get_projects()
                    ]
                    if project_id is None:
                        project_id = project_ids
                    elif project_id not in project_ids:
                        raise permissions.PermissionDenied
                    if permissions.has_supervisor_permissions():
                        department_ids = persons_service.get_current_user(
                            relations=True
                        )["departments"]
                else:
                    raise permissions.PermissionDenied

        return {
            "project_id": project_id,
            "department_ids": department_ids,
        }


class PersonYearTimeSpentsResource(PersonDurationTimeSpentsResource):
    """
    Get aggregated time spents for given person and year.
    """

    @jwt_required()
    def get(self, person_id, year):
        """
        Get aggregated time spents for given person and year.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
        responses:
            200:
                description: Aggregated time spents for given person and year
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_year_time_spents(
                person_id,
                year,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            abort(404)


class PersonMonthTimeSpentsResource(PersonDurationTimeSpentsResource):
    """
    Get aggregated time spents for given person and month.
    """

    @jwt_required()
    def get(self, person_id, year, month):
        """
        Get aggregated time spents for given person and month.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: Aggregated time spents for given person and month
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_month_time_spents(
                person_id,
                year,
                month,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            abort(404)


class PersonMonthAllTimeSpentsResource(Resource):
    """
    Get all time spents for a given person and month.
    """

    @jwt_required()
    def get(self, person_id, year, month):
        user_service.check_person_is_not_bot(person_id)
        user_service.check_person_access(person_id)
        try:
            timespents = time_spents_service.get_time_spents_for_month(
                year, month, person_id=person_id
            )
            return fields.serialize_list(timespents)
        except WrongDateFormatException:
            abort(404)


class PersonWeekTimeSpentsResource(PersonDurationTimeSpentsResource):
    """
    Get aggregated time spents for given person and week.
    """

    @jwt_required()
    def get(self, person_id, year, week):
        """
        Get aggregated time spents for given person and week.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            example: 35
            minimum: 1
            maximum: 52
        responses:
            200:
                description: Aggregated time spents for given person and week
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_week_time_spents(
                person_id,
                year,
                week,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            abort(404)


class PersonDayTimeSpentsResource(PersonDurationTimeSpentsResource):
    """
    Get aggregated time spents for given person and day.
    """

    @jwt_required()
    def get(self, person_id, year, month, day):
        """
        Get aggregated time spents for given person and day.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
          - in: path
            name: day
            required: True
            type: integer
            example: 12
            minimum: 1
            maximum: 31
        responses:
            200:
                description: Aggregated time spents for given person and day
            404:
                description: Wrong date format
        """
        user_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_day_time_spents(
                person_id,
                year,
                month,
                day,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            abort(404)


class PersonQuotaMixin(ArgsMixin):

    def get_quota_arguments(self):
        project_id = self.get_project_id()
        task_type_id = self.get_task_type_id()
        count_mode = self.get_text_parameter("count_mode", default="weighted")
        if count_mode not in ["weighted", "weighteddone", "feedback", "done"]:
            raise WrongParameterException(
                "count_mode must be equal to weighted, weigtheddone, feedback"
                ", or done"
            )
        feedback = "done" not in count_mode
        weighted = "weighted" in count_mode

        return (project_id, task_type_id, feedback, weighted)

    def check_permissions(self, person_id, project_id=None):
        if permissions.has_manager_permissions():
            user_service.check_manager_project_access(project_id)
        else:
            user_service.check_person_access(person_id)

    def get_person_quotas(self):
        pass

    @jwt_required()
    def get(self, person_id, *args, **kwargs):
        user_service.check_person_is_not_bot(person_id)
        (project_id, task_type_id, feedback, weighted) = (
            self.get_quota_arguments()
        )
        self.check_permissions(person_id, project_id)

        try:
            return self.get_person_quotas(
                person_id,
                *args,
                **kwargs,
                project_id=project_id,
                task_type_id=task_type_id,
                feedback=feedback,
                weighted=weighted,
            )
        except WrongDateFormatException:
            abort(404)


class PersonMonthQuotaShotsResource(Resource, PersonQuotaMixin):
    """
    Get ended shots used for quota calculation of this month.
    """

    def get_person_quotas(self, person_id, year, month, **kwargs):
        return shots_service.get_month_quota_shots(
            person_id, year, month, **kwargs
        )

    @jwt_required()
    def get(self, person_id, year, month):
        """
        Get ended shots used for quota calculation of this month.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            example: weighted
        responses:
            200:
                description: Ended shots used for quota calculation of this month
            404:
                description: Wrong date format
        """
        return super().get(person_id, year, month)


class PersonWeekQuotaShotsResource(Resource, PersonQuotaMixin):
    """
    Get ended shots used for quota calculation of this week.
    """

    def get_person_quotas(self, person_id, year, week, **kwargs):
        return shots_service.get_week_quota_shots(
            person_id, year, week, **kwargs
        )

    @jwt_required()
    def get(self, person_id, year, week):
        """
        Get ended shots used for quota calculation of this week.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            example: 35
            minimum: 1
            maximum: 52
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            example: weighted
        responses:
            200:
                description: Ended shots used for quota calculation of this week
            404:
                description: Wrong date format
        """
        return super().get(person_id, year, week)


class PersonDayQuotaShotsResource(Resource, PersonQuotaMixin):
    """
    Get ended shots used for quota calculation of this day.
    """

    def get_person_quotas(self, person_id, year, month, day, **kwargs):
        return shots_service.get_day_quota_shots(
            person_id, year, month, day, **kwargs
        )

    @jwt_required()
    def get(self, person_id, year, month, day):
        """
        Get ended shots used for quota calculation of this day.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
          - in: path
            name: day
            required: True
            type: integer
            example: 12
            minimum: 1
            maximum: 31
          - in: query
            name: count_mode
            required: True
            type: string
            enum: [weighted, weigtheddone, feedback, done]
            example: weighted
        responses:
            200:
                description: Ended shots used for quota calculation of this day
            404:
                description: Wrong date format
        """
        return super().get(person_id, year, month, day)


class TimeSpentDurationResource(Resource, ArgsMixin):
    """
    Parent class for all durations time spents resource.
    """

    def get_person_project_department_arguments(self):
        project_id = self.get_project_id()
        person_id = None
        department_id = self.get_text_parameter("department_id")
        if department_id is not None:
            department_ids = [department_id]
        else:
            department_ids = None
        studio_id = self.get_text_parameter("studio_id")
        if not permissions.has_admin_permissions():
            if (
                permissions.has_manager_permissions()
                or permissions.has_supervisor_permissions()
            ):
                project_ids = [
                    project["id"] for project in user_service.get_projects()
                ]
                if project_id is None:
                    project_id = project_ids
                elif project_id not in project_ids:
                    raise permissions.PermissionDenied
                if permissions.has_supervisor_permissions():
                    persons_departments = persons_service.get_current_user(
                        relations=True
                    )["departments"]
                    if department_id is not None:
                        if department_id not in persons_departments:
                            raise WrongParameterException(
                                "Supervisor not allowed to access this department"
                            )
                    else:
                        department_ids = persons_departments
            else:
                person_id = persons_service.get_current_user()["id"]

        return {
            "person_id": person_id,
            "project_id": project_id,
            "department_ids": department_ids,
            "studio_id": studio_id,
        }


class TimeSpentMonthResource(TimeSpentDurationResource):
    """
    Return a table giving time spent by user and by day for given year and
    month.
    """

    @jwt_required()
    def get(self, year, month):
        """
        Return a table giving time spent by user and by day for given year and month.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: Table giving time spent by user and by day for given year and month
        """

        return time_spents_service.get_day_table(
            year, month, **self.get_person_project_department_arguments()
        )


class TimeSpentYearsResource(TimeSpentDurationResource):
    """
    Return a table giving time spent by user and by month for given year.
    """

    @jwt_required()
    def get(self):
        """
        Return a table giving time spent by user and by month for given year.
        ---
        tags:
        - Persons
        responses:
            200:
                description: Table giving time spent by user and by month for given year
        """
        return time_spents_service.get_year_table(
            **self.get_person_project_department_arguments()
        )


class TimeSpentMonthsResource(TimeSpentDurationResource):
    """
    Return a table giving time spent by user and by month for given year.
    """

    @jwt_required()
    def get(self, year):
        """
        Return a table giving time spent by user and by month for given year.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
        responses:
            200:
                description: Table giving time spent by user and by month for given year
        """
        return time_spents_service.get_month_table(
            year, **self.get_person_project_department_arguments()
        )


class TimeSpentWeekResource(TimeSpentDurationResource):
    """
    Return a table giving time spent by user and by week for given year.
    """

    @jwt_required()
    def get(self, year):
        """
        Return a table giving time spent by user and by week for given year.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
        responses:
            200:
                description: Table giving time spent by user and by week for given year
        """
        return time_spents_service.get_week_table(
            year, **self.get_person_project_department_arguments()
        )


class InvitePersonResource(Resource):
    """
    Sends an email to given person to invite him/her to connect to Kitsu.
    """

    @jwt_required()
    def get(self, person_id):
        """
        Sends an email to given person to invite him/her to connect to Kitsu.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Email sent
        """
        user_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        persons_service.invite_person(person_id)
        return {"success": True, "message": "Email sent"}


class DayOffForMonthResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given month.
    """

    @jwt_required()
    def get(self, year, month):
        """
        Return all day off recorded for given month.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: All day off recorded for given month
        """
        if permissions.has_admin_permissions():
            return time_spents_service.get_day_offs_for_month(year, month)
        else:
            person_id = persons_service.get_current_user()["id"]
            return time_spents_service.get_person_day_offs_for_month(
                person_id, year, month
            )


class PersonWeekDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given week and person.
    """

    @jwt_required()
    def get(self, person_id, year, week):
        """
        Return all day off recorded for given week and person.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            example: 35
            minimum: 1
            maximum: 52
        responses:
            200:
                description: All day off recorded for given week and person
        """
        user_service.check_person_is_not_bot(person_id)
        user_service.check_person_access(person_id)
        return time_spents_service.get_person_day_offs_for_week(
            person_id, year, week
        )


class PersonMonthDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given month and person.
    """

    @jwt_required()
    def get(self, person_id, year, month):
        """
        Return all day off recorded for given month and person.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: All day off recorded for given month and person
        """
        user_service.check_person_is_not_bot(person_id)
        user_service.check_person_access(person_id)
        return time_spents_service.get_person_day_offs_for_month(
            person_id, year, month
        )


class PersonYearDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given year and person.
    """

    @jwt_required()
    def get(self, person_id, year):
        """
        Return all day off recorded for given year and person.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            example: "2022"
        responses:
            200:
                description: All day off recorded for given year and person
        """
        user_service.check_person_is_not_bot(person_id)
        user_service.check_person_access(person_id)
        return time_spents_service.get_person_day_offs_for_year(
            person_id, year
        )


class PersonDayOffResource(Resource, ArgsMixin):
    """
    Return all day offs recorded for given and person.
    """

    @jwt_required()
    def get(self, person_id):
        """
        Return all day offs recorded for given and person.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All day off recorded for given person.
        """
        user_service.check_person_is_not_bot(person_id)
        user_service.check_person_access(person_id)
        return time_spents_service.get_day_offs_between(
            person_id=person_id,
        )


class AddToDepartmentResource(Resource, ArgsMixin):
    """
    Add a user to given department.
    """

    @jwt_required()
    def post(self, person_id):
        """
        Add a user to given department.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: User added to given department
        """
        args = self.get_args(
            [
                ("department_id", None, True),
            ]
        )

        permissions.check_admin_permissions()

        try:
            department = tasks_service.get_department(args["department_id"])
        except DepartmentNotFoundException:
            raise WrongParameterException(
                "Department ID matches no department"
            )
        person = persons_service.add_to_department(department["id"], person_id)
        return person, 201


class RemoveFromDepartmentResource(Resource, ArgsMixin):
    """
    Remove a user from given department.
    """

    @jwt_required()
    def delete(self, person_id, department_id):
        """
        Remove a user from given department.
        ---
        tags:
        - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: department_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: User removed from given department
        """
        permissions.check_admin_permissions()
        try:
            tasks_service.get_department(department_id)
        except DepartmentNotFoundException:
            raise WrongParameterException(
                "Department ID matches no department"
            )
        persons_service.remove_from_department(department_id, person_id)
        return "", 204


class ChangePasswordForPersonResource(Resource, ArgsMixin):
    """
    Allow admin to change password for given user.
    """

    @jwt_required()
    def post(self, person_id):
        """
        Allow admin to change password for given user.
        ---
        description: Prior to modifying the password, it requires to be admin.
                     An admin can't change other admins password.
                     The new password requires a confirmation to ensure that the admin didn't
                     make a mistake by typing the new password.
        tags:
            - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: password
            required: True
            type: string
            format: password
          - in: formData
            name: password_2
            required: True
            type: string
            format: password
        responses:
          200:
            description: Password changed
          400:
            description: Invalid password or inactive user
        """
        user_service.check_person_is_not_bot(person_id)
        (password, password_2) = self.get_arguments()
        permissions.check_admin_permissions()
        try:
            person = persons_service.get_person(person_id)
            if (
                person["email"] in config.PROTECTED_ACCOUNTS
                and person["id"] != persons_service.get_current_user()["id"]
            ):
                raise PersonInProtectedAccounts()
            current_user = persons_service.get_current_user()
            auth.validate_password(password, password_2)
            password = auth.encrypt_password(password)
            persons_service.update_password(person["email"], password)
            current_app.logger.warning(
                "User %s has changed the password of %s"
                % (current_user["email"], person["email"])
            )
            organisation = persons_service.get_organisation()
            time_string = format_datetime(
                date_helpers.get_utc_now_datetime(),
                tzinfo=person["timezone"],
                locale=person["locale"],
            )
            person_IP = request.headers.get("X-Forwarded-For", None)
            html = f"""<p>Hello {person["first_name"]},</p>
<p>
Your password was changed at this date: {time_string}.
The IP of the user who changed your password is: {person_IP}.
If you don't know the person who changed the password, please contact our support team.
</p>
Thank you and see you soon on Kitsu,
</p>
<p>
{organisation["name"]} Team
</p>
"""
            subject = f"{organisation['name']} - Kitsu: password changed"
            emails.send_email(subject, html, person["email"])
            return {"success": True}

        except auth.PasswordsNoMatchException:
            return (
                {
                    "error": True,
                    "message": "Confirmation password doesn't match.",
                },
                400,
            )
        except auth.PasswordTooShortException:
            return {"error": True, "message": "Password is too short."}, 400
        except UnactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except PersonInProtectedAccounts:
            return (
                {
                    "error": True,
                    "message": "This user is in protected accounts.",
                },
                400,
            )

    def get_arguments(self):
        args = self.get_args(
            [
                {
                    "name": "password",
                    "required": True,
                    "help": "New password is missing.",
                },
                {
                    "name": "password_2",
                    "required": True,
                    "help": "New password confirmation is missing.",
                },
            ]
        )

        return (args["password"], args["password_2"])


class DisableTwoFactorAuthenticationPersonResource(Resource, ArgsMixin):
    """
    Allow admin to disable two factor authentication for given user.
    """

    @jwt_required()
    def delete(self, person_id):
        """
        Allow admin to disable two factor authentication for given user.
        ---
        description: Prior to disable two factor authentication, it requires to
                     be admin.
                     An admin can't disable two factor authentication for other
                     admins.
        tags:
            - Persons
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
          200:
            description: Two factor authentication disabled
          400:
            description: Inactive user
        """
        user_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        try:
            person = persons_service.get_person(person_id)
            current_user = persons_service.get_current_user()
            disable_two_factor_authentication_for_person(person["id"])
            current_app.logger.warning(
                "User %s has disabled the two factor authentication of %s"
                % (current_user["email"], person["email"])
            )
            organisation = persons_service.get_organisation()
            time_string = format_datetime(
                date_helpers.get_utc_now_datetime(),
                tzinfo=person["timezone"],
                locale=person["locale"],
            )
            person_IP = request.headers.get("X-Forwarded-For", None)
            html = f"""<p>Hello {person["first_name"]},</p>
<p>
Your two factor authentication was disabled at this date: {time_string}.
The IP of the user who disabled your two factor authentication is: {person_IP}.
If you don't know the person who disabled the two factor authentication, please contact our support team.
</p>
Thank you and see you soon on Kitsu,
</p>
<p>
{organisation["name"]} Team
</p>
"""
            subject = f"{organisation['name']} - Kitsu: two factor authentication disabled"
            emails.send_email(subject, html, person["email"])
            return {"success": True}

        except UnactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except TwoFactorAuthenticationNotEnabledException:
            return {
                "error": True,
                "message": "Two factor authentication not enabled for this user.",
            }, 400


class ClearAvatarPersonResource(Resource):
    @jwt_required()
    def delete(self, person_id):
        """
        Set `has_avatar` flag to False for current user and remove its avatar
        file.
        ---
        tags:
          - User
        responses:
            204:
                description: Avatar file deleted
        """
        permissions.check_admin_permissions()
        persons_service.clear_avatar(person_id)
        return "", 204
