import datetime

from flask import abort
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app import config, name_space_persons, name_space_actions_persons
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


@name_space_persons.route('/new')
class NewPersonResource(Resource):

    @jwt_required
    def post(self):
        """
        Create a new user in the database. Set "default" as password.
        User role can be set but only admins can create admin users.
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


@name_space_persons.route('/<person_id>/desktop-login-logs')
class DesktopLoginsResource(Resource):

    @jwt_required
    def get(self, person_id):
        """
        Allow to retrieve desktop login logs. Desktop login logs can only
        be created by current user.
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
        Allow to create desktop login logs. Desktop login logs can only
        be created by current user.
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


@name_space_persons.route('/presence-logs/<month_date>')
class PresenceLogsResource(Resource):

    @jwt_required
    def get(self, month_date):
        """
        Return a csv file containing the presence logs based on a daily basis.
        """
        permissions.check_admin_permissions()
        date = datetime.datetime.strptime(month_date, "%Y-%m")
        presence_logs = persons_service.get_presence_logs(
            date.year, date.month
        )
        return csv_utils.build_csv_response(presence_logs)


@name_space_persons.route('/<person_id>/time-spents/<date>')
class TimeSpentsResource(Resource):

    @jwt_required
    def get(self, person_id, date):
        """
        Get time spents for given person and date.
        """
        permissions.check_manager_permissions()
        try:
            return time_spents_service.get_time_spents(person_id, date)
        except WrongDateFormatException:
            abort(404)


@name_space_persons.route('/<person_id>/day-offs/<date>')
class DayOffResource(Resource):

    @jwt_required
    def get(self, person_id, date):
        """
        Get day off object for given person and date.
        """
        current_user = persons_service.get_current_user()
        if current_user["id"] != person_id:
            permissions.check_manager_permissions()
        try:
            return time_spents_service.get_day_off(person_id, date)
        except WrongDateFormatException:
            abort(404)


@name_space_persons.route('/<person_id>/time-spents/year/<year>')
class PersonYearTimeSpentsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year):
        """
        Get aggregated time spents for given person and year.
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_year_time_spents(
                person_id, year, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


@name_space_persons.route('/<person_id>/time-spents/month/<year>/<month>')
class PersonMonthTimeSpentsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, month):
        """
        Get aggregated time spents for given person and month.
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_month_time_spents(
                person_id, year, month, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


@name_space_persons.route('/<person_id>/time-spents/week/<year>/<week>')
class PersonWeekTimeSpentsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, week):
        """
        Get aggregated time spents for given person and week.
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_week_time_spents(
                person_id, year, week, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)


@name_space_persons.route('/<person_id>/time-spents/day/<year>/<month>/<day>')
class PersonDayTimeSpentsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, month, day):
        """
        Get aggregated time spents for given person and day.
        """
        project_id = self.get_project_id()
        user_service.check_person_access(person_id)
        try:
            return time_spents_service.get_day_time_spents(
                person_id, year, month, day, project_id=project_id
            )
        except WrongDateFormatException:
            abort(404)

@name_space_persons.route('/<person_id>/quota-shots/month/<year>/<month>')
class PersonMonthQuotaShotsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, month):
        """
        Get ended shots used for quota calculation of this month.
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


@name_space_persons.route('/<person_id>/quota-shots/week/<year>/<week>')
class PersonWeekQuotaShotsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, week):
        """
        Get ended shots used for quota calculation of this week.
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


@name_space_persons.route('/<person_id>/quota-shots/day/<year>/<month>/<day>')
class PersonDayQuotaShotsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, month, day):
        """
        Get ended shots used for quota calculation of this day.
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


@name_space_persons.route('/time-spents/day-table/<year>/<month>')
class TimeSpentMonthResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, year, month):
        """
        Return a table giving time spent by user and by day for given year and
        month.
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_day_table(
            year, month, person_id=person_id, project_id=project_id
        )


@name_space_persons.route('/time-spents/year-table/')
class TimeSpentYearsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self):
        """
        Return a table giving time spent by user and by month for given year.
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_year_table(
            person_id=person_id, project_id=project_id
        )


@name_space_persons.route('/time-spents/month-table/<year>')
class TimeSpentMonthsResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, year):
        """
        Return a table giving time spent by user and by month for given year.
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_month_table(
            year, person_id=person_id, project_id=project_id
        )


@name_space_persons.route('/time-spents/week-table/<year>')
class TimeSpentWeekResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, year):
        """
        Return a table giving time spent by user and by week for given year.
        """
        project_id = self.get_project_id()
        person_id = None
        if not permissions.has_admin_permissions():
            person_id = persons_service.get_current_user()["id"]
        return time_spents_service.get_week_table(
            year, person_id=person_id, project_id=project_id
        )


@name_space_actions_persons.route('/<person_id>/invite')
class InvitePersonResource(Resource):

    @jwt_required
    def get(self, person_id):
        """
        Sends an email to given person to invite him/her to connect to Kitsu.
        """
        permissions.check_admin_permissions()
        persons_service.invite_person(person_id)
        return {"success": True, "message": "Email sent"}


@name_space_persons.route('/day-offs/<year>/<month>')
class DayOffForMonthResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, year, month):
        """
        Return all day off recorded for given month.
        """
        if permissions.has_admin_permissions():
            return time_spents_service.get_day_offs_for_month(year, month)
        else:
            person_id = persons_service.get_current_user()["id"]
            return time_spents_service.get_person_day_offs_for_month(
                person_id, year, month
            )

@name_space_persons.route('/<person_id>/day-offs/week/<year>/<week>')
class PersonWeekDayOffResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, week):
        """
        Return all day off recorded for given week and person.
        """
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_week(
            person_id, year, week
        )


@name_space_persons.route('/<person_id>/day-offs/month/<year>/<month>')
class PersonMonthDayOffResource(Resource, ArgsMixin):

    @jwt_required
    def get(self, person_id, year, month):
        """
        Return all day off recorded for given month and person.
        """
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_month(
            person_id, year, month
        )


@name_space_persons.route('/<person_id>/day-offs/year/<year>')
class PersonYearDayOffResource(Resource, ArgsMixin):
    """
    Return all day off recorded for given year and person.
    """

    @jwt_required
    def get(self, person_id, year):
        user_id = persons_service.get_current_user()["id"]
        if person_id != user_id:
            permissions.check_admin_permissions()
        return time_spents_service.get_person_day_offs_for_year(
            person_id, year
        )


@name_space_actions_persons.route('/<person_id>/departments/add')
class AddToDepartmentResource(Resource, ArgsMixin):

    @jwt_required
    def post(self, person_id):
        """
        Add a user to given department.
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


@name_space_actions_persons.route('/<person_id>/departments/<department_id>')
class RemoveFromDepartmentResource(Resource, ArgsMixin):

    @jwt_required
    def delete(self, person_id, department_id):
        """
        Remove a user from given department.
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
