import datetime

from flask import abort
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app import config
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    persons_service,
    tasks_service,
    time_spents_service,
    shots_service,
    user_service,
)
from zou.app.utils import auth, permissions, csv_utils
from zou.app.services.exception import (
    DepartmentNotFoundException,
    WrongDateFormatException,
    WrongParameterException,
)


class NewPersonResource(Resource):
    """
    Create a new user in the database. Set "default" as password.
    User role can be set but only admins can create admin users.
    """

    @jwt_required
    def post(self):
        """
        Create a new user in the database.
        ---
        tags:
        - Persons
        description: Set "default" as password.
                     User role can be set but only admins can create admin users.
        parameters:
          - in: formData
            name: email
            required: True
            type: string
            format: email
            x-example: admin@example.com
          - in: formData
            name: phone
            required: False
            type: integer
            x-example: 06 12 34 56 78
          - in: formData
            name: role
            required: False
            type: string
            x-example: user
          - in: formData
            name: first_name
            required: True
            type: string
          - in: formData
            name: last_name
            required: False
            type: string
        responses:
            201:
                description: User created
        """
        permissions.check_admin_permissions()
        data = self.get_arguments()

        if persons_service.is_user_limit_reached():
            return {
                "error": True,
                "message": "User limit reached.",
                "limit": config.USER_LIMIT,
            }, 400
        else:
            person = persons_service.create_person(
                data["email"],
                auth.encrypt_password("default"),
                data["first_name"],
                data["last_name"],
                data["phone"],
                role=data["role"],
                desktop_login=data["desktop_login"],
                departments=data["departments"],
            )
        return person, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "email", help="The email is required.", required=True
        )
        parser.add_argument(
            "first_name", help="The first name is required.", required=True
        )
        parser.add_argument("last_name", default="")
        parser.add_argument("phone", default="")
        parser.add_argument("role", default="user")
        parser.add_argument("desktop_login", default="")
        parser.add_argument("departments", default=None, action="append")
        args = parser.parse_args()
        return args


class DesktopLoginsResource(Resource):
    """
    Allow to create and retrieve desktop login logs. Desktop login logs can only
    be created by current user.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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

    @jwt_required
    def post(self, person_id):
        """
        Create desktop login logs.
        ---
        tags:
        - Persons
        description: Set "default" as password.
                     User role can be set but only admins can create admin users.
        parameters:
          - in: path
            name: person_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formDara
            name: date
            required: True
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            201:
                description: Desktop login logs created
        """
        arguments = self.get_arguments()

        current_user = persons_service.get_current_user()
        if (
            current_user["id"] != person_id
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied

        desktop_login_log = persons_service.create_desktop_login_logs(
            person_id, arguments["date"]
        )

        return desktop_login_log, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument("date", default=datetime.datetime.now())
        return parser.parse_args()


class PresenceLogsResource(Resource):
    """
    Return a csv file containing the presence logs based on a daily basis.
    """

    @jwt_required
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
            x-example: "2022-07"
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


class TimeSpentsResource(Resource):
    """
    Get time spents for given person and date.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: True
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            200:
                description: Time spents for given person and date
            404:
                description: Wrong date format
        """
        current_user = persons_service.get_current_user()
        if current_user["id"] != person_id:
            try:
                permissions.check_at_least_supervisor_permissions()
            except permissions.PermissionDenied:
                return []
        try:
            return time_spents_service.get_time_spents(person_id, date)
        except WrongDateFormatException:
            abort(404)


class DayOffResource(Resource):
    """
    Get day off object for given person and date.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: date
            required: True
            type: string
            format: date
            x-example: "2022-07-12"
        responses:
            200:
                description: Day off object for given person and date
            404:
                description: Wrong date format
        """
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


class PersonYearTimeSpentsResource(Resource, ArgsMixin):
    """
    Get aggregated time spents for given person and year.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
        responses:
            200:
                description: Aggregated time spents for given person and year
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_year_time_spents(
                person_id, year, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


class PersonMonthTimeSpentsResource(Resource, ArgsMixin):
    """
    Get aggregated time spents for given person and month.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: Aggregated time spents for given person and month
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_month_time_spents(
                person_id, year, month, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


class PersonWeekTimeSpentsResource(Resource, ArgsMixin):
    """
    Get aggregated time spents for given person and week.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            x-example: 35
            minimum: 1
            maximum: 52
        responses:
            200:
                description: Aggregated time spents for given person and week
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_week_time_spents(
                person_id, year, week, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


class PersonDayTimeSpentsResource(Resource, ArgsMixin):
    """
    Get aggregated time spents for given person and day.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
          - in: path
            name: day
            required: True
            type: integer
            x-example: 12
            minimum: 1
            maximum: 31
        responses:
            200:
                description: Aggregated time spents for given person and day
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_day_time_spents(
                person_id, year, month, day, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


class PersonMonthQuotaShotsResource(Resource, ArgsMixin):
    """
    Get ended shots used for quota calculation of this month.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: Ended shots used for quota calculation of this month
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        task_type_id = self.get_task_type_id()
        user_service.check_person_access(person_id)
        weighted = self.get_bool_parameter("weighted", default="true")
        try:
            return shots_service.get_month_quota_shots(
                person_id,
                year,
                month,
                project_id=project_id,
                task_type_id=task_type_id,
                weighted=weighted,
            )
        except WrongDateFormatException:
            abort(404)


class PersonWeekQuotaShotsResource(Resource, ArgsMixin):
    """
    Get ended shots used for quota calculation of this week.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            x-example: 35
            minimum: 1
            maximum: 52
        responses:
            200:
                description: Ended shots used for quota calculation of this week
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        task_type_id = self.get_task_type_id()
        user_service.check_person_access(person_id)
        weighted = self.get_bool_parameter("weighted", default="true")
        try:
            return shots_service.get_week_quota_shots(
                person_id,
                year,
                week,
                project_id=project_id,
                task_type_id=task_type_id,
                weighted=weighted,
            )
        except WrongDateFormatException:
            abort(404)


class PersonDayQuotaShotsResource(Resource, ArgsMixin):
    """
    Get ended shots used for quota calculation of this day.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
          - in: path
            name: day
            required: True
            type: integer
            x-example: 12
            minimum: 1
            maximum: 31
        responses:
            200:
                description: Ended shots used for quota calculation of this day
            404:
                description: Wrong date format
        """
        project_id = self.get_project_id()
        task_type_id = self.get_task_type_id()
        user_service.check_person_access(person_id)
        weighted = self.get_bool_parameter("weighted", default="true")
        try:
            return shots_service.get_day_quota_shots(
                person_id,
                year,
                month,
                day,
                project_id=project_id,
                task_type_id=task_type_id,
                weighted=weighted,
            )
        except WrongDateFormatException:
            abort(404)


class TimeSpentMonthResource(Resource, ArgsMixin):
    """
    Return a table giving time spent by user and by day for given year and
    month.
    """

    @jwt_required
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
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: Table giving time spent by user and by day for given year and month
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_day_table(
            year, month, person_id=person_id, project_id=project_id
        )


class TimeSpentYearsResource(Resource, ArgsMixin):
    """
    Return a table giving time spent by user and by month for given year.
    """

    @jwt_required
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
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_year_table(
            person_id=person_id, project_id=project_id
        )


class TimeSpentMonthsResource(Resource, ArgsMixin):
    """
    Return a table giving time spent by user and by month for given year.
    """

    @jwt_required
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
            x-example: "2022"
        responses:
            200:
                description: Table giving time spent by user and by month for given year
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_month_table(
            year, person_id=person_id, project_id=project_id
        )


class TimeSpentWeekResource(Resource, ArgsMixin):
    """
    Return a table giving time spent by user and by week for given year.
    """

    @jwt_required
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
            x-example: "2022"
        responses:
            200:
                description: Table giving time spent by user and by week for given year
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_week_table(
            year, person_id=person_id, project_id=project_id
        )


class InvitePersonResource(Resource):
    """
    Sends an email to given person to invite him/her to connect to Kitsu.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Email sent
        """
        permissions.check_admin_permissions()
        persons_service.invite_person(person_id)
        return {"success": True, "message": "Email sent"}


class DayOffForMonthResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given month.
    """

    @jwt_required
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
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
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

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: week
            required: True
            type: integer
            x-example: 35
            minimum: 1
            maximum: 52
        responses:
            200:
                description: All day off recorded for given week and person
        """
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_week(
            person_id, year, week
        )


class PersonMonthDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given month and person.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
          - in: path
            name: month
            required: True
            type: integer
            x-example: 07
            minimum: 1
            maximum: 12
        responses:
            200:
                description: All day off recorded for given month and person
        """
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_month(
            person_id, year, month
        )


class PersonYearDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given year and person.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: year
            required: True
            type: integer
            x-example: "2022"
        responses:
            200:
                description: All day off recorded for given year and person
        """
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_year(
            person_id, year
        )


class AddToDepartmentResource(Resource, ArgsMixin):
    """
    Add a user to given department.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            201:
                description: User added to given department
        """
        permissions.check_admin_permissions()
        args = self.get_args(
            [
                ("department_id", None, True),
            ]
        )
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

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: department_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: User removed from given department
        """
        permissions.check_admin_permissions()
        try:
            department = tasks_service.get_department(department_id)
        except DepartmentNotFoundException:
            raise WrongParameterException(
                "Department ID matches no department"
            )
        persons_service.remove_from_department(department_id, person_id)
        return "", 204
