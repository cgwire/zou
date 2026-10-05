from flasgger import swag_from
import datetime
import ipaddress

from flask import request, current_app
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.services import (
    persons_service,
    tasks_service,
    time_spents_service,
    shots_service,
    permissions_service,
    user_service,
)
from zou.app.utils import (
    permissions,
    csv_utils,
    auth,
    fields,
    date_helpers,
    validation,
)
from zou.app.blueprints.persons.schemas import (
    DesktopLoginCreateSchema,
    AddToDepartmentSchema,
    ChangePasswordSchema,
)
from zou.app.exceptions import (
    DepartmentNotFoundException,
    WrongDateFormatException,
    WrongParameterException,
    InactiveUserException,
    TwoFactorAuthenticationNotEnabledException,
    PersonInProtectedAccounts,
)
from zou.app.services.auth_service import (
    disable_two_factor_authentication_for_person,
)


def _get_project_department_ids_for_person_access(person_id):
    """
    Returns (project_ids, department_ids) for the current user when accessing
    the given person_id. For admin or when person_id is the current user,
    returns (None, None). For manager/supervisor returns (project_ids, department_ids).
    Raises PermissionDenied otherwise.
    """
    if permissions.has_admin_permissions():
        return (None, None)
    current_user_id = persons_service.get_current_user()["id"]
    if current_user_id == person_id:
        return (None, None)
    if not (
        permissions.has_manager_permissions()
        or permissions.has_supervisor_permissions()
    ):
        raise permissions.PermissionDenied
    project_ids = [p["id"] for p in user_service.get_projects()]
    department_ids = None
    if permissions.has_supervisor_permissions():
        department_ids = persons_service.get_current_user(relations=True).get(
            "departments", []
        )
    return (project_ids, department_ids)


def _check_day_off_read_access(person_id):
    """
    Guard a day off read of given person, the rule being
    permissions_service.check_day_off_read_access: return whether the
    description is part of what the caller gets.
    """
    permissions_service.check_person_is_not_bot(person_id)
    return permissions_service.check_day_off_read_access(person_id)


def _dates_only(day_off):
    """
    Given serialized day off without its description, what a supervisor
    gets to see of it.
    """
    return {
        key: value for key, value in day_off.items() if key != "description"
    }


def _shape_day_offs(day_offs, with_description):
    """
    Serialized day offs as the caller gets them: whole, or the dates only.
    """
    if with_description:
        return day_offs
    return [_dates_only(day_off) for day_off in day_offs]


class DesktopLoginsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/DesktopLoginsResource_get.yml")
    def get(self, person_id):
        """
        Get desktop login logs
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
    @swag_from("openapi/DesktopLoginsResource_post.yml")
    def post(self, person_id):
        """
        Create desktop login log
        """
        body = validation.validate_request_body(DesktopLoginCreateSchema)
        date = (
            body.date
            if body.date is not None
            else date_helpers.get_utc_now_datetime()
        )

        current_user = persons_service.get_current_user()
        if (
            current_user["id"] != person_id
            and not permissions.has_admin_permissions()
        ):
            raise permissions.PermissionDenied

        desktop_login_log = persons_service.create_desktop_login_logs(
            person_id, date
        )

        return desktop_login_log, 201


class PresenceLogsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PresenceLogsResource_get.yml")
    def get(self, month_date):
        """
        Get presence logs
        """
        permissions.check_admin_permissions()
        try:
            date = datetime.datetime.strptime(month_date, "%Y-%m")
        except ValueError:
            raise WrongParameterException("Invalid month or year.")
        presence_logs = persons_service.get_presence_logs(
            date.year, date.month
        )
        return csv_utils.build_csv_response(presence_logs)


class TimeSpentsResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/TimeSpentsResource_get.yml")
    def get(self, person_id):
        """
        Get time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        arguments = self.get_args(["start_date", "end_date"])
        start_date, end_date = arguments["start_date"], arguments["end_date"]
        if not start_date and not end_date:
            return time_spents_service.get_time_spents(person_id)

        if None in [start_date, end_date]:
            raise WrongParameterException(
                "If querying for a range of dates, both a `start_date` and"
                " an `end_date` must be given."
            )

        try:
            return time_spents_service.get_time_spents_range(
                person_id, start_date, end_date
            )
        except WrongDateFormatException:
            raise WrongParameterException(
                f"Wrong date format for {start_date} and/or {end_date}"
            )


class DateTimeSpentsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/DateTimeSpentsResource_get.yml")
    def get(self, person_id, date):
        """
        Get time spents for date
        """
        permissions_service.check_person_is_not_bot(person_id)
        project_ids, department_ids = (
            _get_project_department_ids_for_person_access(person_id)
        )
        try:
            return time_spents_service.get_time_spents(
                person_id,
                date,
                project_ids=project_ids,
                department_ids=department_ids,
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid month or year.")


class DayOffResource(MethodView):

    @jwt_required()
    @swag_from("openapi/DayOffResource_get.yml")
    def get(self, person_id, date):
        """
        Get day off
        """
        with_description = _check_day_off_read_access(person_id)
        try:
            day_off = time_spents_service.get_day_off(person_id, date)
        except WrongDateFormatException:
            raise WrongParameterException("Invalid date format.")
        return day_off if with_description else _dates_only(day_off)


class PersonDurationTimeSpentsResource(MethodView, ArgsMixin):

    def get_project_department_arguments(self, person_id):
        project_id = self.get_project_id()
        project_ids, department_ids = (
            _get_project_department_ids_for_person_access(person_id)
        )
        if project_ids is not None:
            if project_id is None:
                project_id = project_ids
            elif project_id not in project_ids:
                raise permissions.PermissionDenied
        return {
            "project_id": project_id,
            "department_ids": department_ids,
        }


class PersonYearTimeSpentsResource(PersonDurationTimeSpentsResource):

    @jwt_required()
    @swag_from("openapi/PersonYearTimeSpentsResource_get.yml")
    def get(self, person_id, year):
        """
        Get year time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_year_time_spents(
                person_id,
                year,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid date format.")


class PersonMonthTimeSpentsResource(PersonDurationTimeSpentsResource):

    @jwt_required()
    @swag_from("openapi/PersonMonthTimeSpentsResource_get.yml")
    def get(self, person_id, year, month):
        """
        Get month time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_month_time_spents(
                person_id,
                year,
                month,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid date format.")


class PersonMonthAllTimeSpentsResource(MethodView):

    @jwt_required()
    @swag_from("openapi/PersonMonthAllTimeSpentsResource_get.yml")
    def get(self, person_id, year, month):
        """
        Get all month time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions_service.check_person_access(person_id)
        try:
            timespents = time_spents_service.get_time_spents_for_month(
                year, month, person_id=person_id
            )
            return fields.serialize_list(timespents)
        except WrongDateFormatException:
            raise WrongParameterException("Invalid month or year.")


class PersonWeekTimeSpentsResource(PersonDurationTimeSpentsResource):

    @jwt_required()
    @swag_from("openapi/PersonWeekTimeSpentsResource_get.yml")
    def get(self, person_id, year, week):
        """
        Get week time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_week_time_spents(
                person_id,
                year,
                week,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid month or year.")


class PersonDayTimeSpentsResource(PersonDurationTimeSpentsResource):

    @jwt_required()
    @swag_from("openapi/PersonDayTimeSpentsResource_get.yml")
    def get(self, person_id, year, month, day):
        """
        Get day time spents
        """
        permissions_service.check_person_is_not_bot(person_id)
        try:
            return time_spents_service.get_day_time_spents(
                person_id,
                year,
                month,
                day,
                **self.get_project_department_arguments(person_id),
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid month or year.")


class PersonQuotaMixin(ArgsMixin):

    def get_quota_arguments(self):
        project_id = self.get_project_id()
        task_type_id = self.get_task_type_id()
        count_mode = self.get_text_parameter("count_mode", default="weighted")
        if count_mode not in ["weighted", "weighteddone", "feedback", "done"]:
            raise WrongParameterException(
                "count_mode must be equal to weighted, weighteddone, feedback"
                ", or done"
            )
        feedback = "done" not in count_mode
        weighted = "weighted" in count_mode

        return (project_id, task_type_id, feedback, weighted)

    def check_permissions(self, person_id, project_id=None):
        permissions_service.resolve_project_role(project_id)
        if permissions.has_manager_permissions():
            permissions_service.check_manager_project_access(project_id)
        else:
            permissions_service.check_person_access(person_id)

    def get_person_quotas(self):
        pass

    @jwt_required()
    def get(self, person_id, *args, **kwargs):
        permissions_service.check_person_is_not_bot(person_id)
        project_id, task_type_id, feedback, weighted = (
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
            raise WrongParameterException("Invalid month or year.")


class PersonMonthQuotaShotsResource(MethodView, PersonQuotaMixin):

    def get_person_quotas(self, person_id, year, month, **kwargs):
        return shots_service.get_month_quota_shots(
            person_id, year, month, **kwargs
        )

    @jwt_required()
    @swag_from("openapi/PersonMonthQuotaShotsResource_get.yml")
    def get(self, person_id, year, month):
        """
        Get month quota shots
        """
        return super().get(person_id, year, month)


class PersonWeekQuotaShotsResource(MethodView, PersonQuotaMixin):

    def get_person_quotas(self, person_id, year, week, **kwargs):
        return shots_service.get_week_quota_shots(
            person_id, year, week, **kwargs
        )

    @jwt_required()
    @swag_from("openapi/PersonWeekQuotaShotsResource_get.yml")
    def get(self, person_id, year, week):
        """
        Get week quota shots
        """
        return super().get(person_id, year, week)


class PersonDayQuotaShotsResource(MethodView, PersonQuotaMixin):

    def get_person_quotas(self, person_id, year, month, day, **kwargs):
        return shots_service.get_day_quota_shots(
            person_id, year, month, day, **kwargs
        )

    @jwt_required()
    @swag_from("openapi/PersonDayQuotaShotsResource_get.yml")
    def get(self, person_id, year, month, day):
        """
        Get day quota shots
        """
        return super().get(person_id, year, month, day)


class TimeSpentDurationResource(MethodView, ArgsMixin):
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

    @jwt_required()
    @swag_from("openapi/TimeSpentMonthResource_get.yml")
    def get(self, year, month):
        """
        Get time spent month table
        """
        try:
            return time_spents_service.get_day_table(
                year, month, **self.get_person_project_department_arguments()
            )
        except WrongDateFormatException:
            raise WrongParameterException("Invalid month or year.")


class TimeSpentYearsResource(TimeSpentDurationResource):

    @jwt_required()
    @swag_from("openapi/TimeSpentYearsResource_get.yml")
    def get(self):
        """
        Get time spent years table
        """
        return time_spents_service.get_year_table(
            **self.get_person_project_department_arguments()
        )


class TimeSpentMonthsResource(TimeSpentDurationResource):

    @jwt_required()
    @swag_from("openapi/TimeSpentMonthsResource_get.yml")
    def get(self, year):
        """
        Get time spent months table
        """
        return time_spents_service.get_month_table(
            year, **self.get_person_project_department_arguments()
        )


class TimeSpentWeekResource(TimeSpentDurationResource):

    @jwt_required()
    @swag_from("openapi/TimeSpentWeekResource_get.yml")
    def get(self, year):
        """
        Get time spent weeks table
        """
        return time_spents_service.get_week_table(
            year, **self.get_person_project_department_arguments()
        )


class InvitePersonResource(MethodView):

    @jwt_required()
    @swag_from("openapi/InvitePersonResource_get.yml")
    def get(self, person_id):
        """
        Invite person
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        persons_service.invite_person(person_id)
        return {"success": True, "message": "Email sent"}


class ResetPasswordLinkResource(MethodView):

    @jwt_required()
    @swag_from("openapi/ResetPasswordLinkResource_post.yml")
    def post(self, person_id):
        """
        Get a password reset link
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        current_user = persons_service.get_current_user()
        try:
            person = persons_service.check_password_change_allowed(person_id)
            reset_password_link = (
                persons_service.get_or_create_password_reset_link(person_id)
            )
            current_app.logger.info(
                f"User {current_user['email']} generated a password reset "
                f"link for {person['email']}"
            )
            return {"reset_password_link": reset_password_link}
        except PersonInProtectedAccounts as exception:
            return {"error": True, "message": exception.description}, 400


class DayOffForMonthResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/DayOffForMonthResource_get.yml")
    def get(self, year, month):
        """
        Get day offs for month
        """
        return _readable_day_offs(
            time_spents_service.get_day_offs_for_month, year, month
        )


class DayOffForYearResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/DayOffForYearResource_get.yml")
    def get(self, year):
        """
        Get day offs for year
        """
        return _readable_day_offs(
            time_spents_service.get_day_offs_for_year, year
        )


def _readable_day_offs(list_period, *period):
    """
    The day offs of the period, scoped to the persons the caller may read,
    with the descriptions of the ones the caller may read in full.
    """
    readable = permissions_service.get_day_off_readable_person_ids()
    if readable is None:
        return list_period(*period)
    day_offs = list_period(*period, person_ids=list(readable.keys()))
    return [
        day_off if readable[day_off["person_id"]] else _dates_only(day_off)
        for day_off in day_offs
    ]


class PersonWeekDayOffResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PersonWeekDayOffResource_get.yml")
    def get(self, person_id, year, week):
        """
        Get person week day offs
        """
        with_description = _check_day_off_read_access(person_id)
        return _shape_day_offs(
            time_spents_service.get_person_day_offs_for_week(
                person_id, year, week
            ),
            with_description,
        )


class PersonMonthDayOffResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PersonMonthDayOffResource_get.yml")
    def get(self, person_id, year, month):
        """
        Get person month day offs
        """
        with_description = _check_day_off_read_access(person_id)
        return _shape_day_offs(
            time_spents_service.get_person_day_offs_for_month(
                person_id, year, month
            ),
            with_description,
        )


class PersonYearDayOffResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PersonYearDayOffResource_get.yml")
    def get(self, person_id, year):
        """
        Get person year day offs
        """
        with_description = _check_day_off_read_access(person_id)
        return _shape_day_offs(
            time_spents_service.get_person_day_offs_for_year(person_id, year),
            with_description,
        )


class PersonDayOffResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/PersonDayOffResource_get.yml")
    def get(self, person_id):
        """
        Get person day offs
        """
        with_description = _check_day_off_read_access(person_id)
        return _shape_day_offs(
            time_spents_service.get_day_offs_between(person_id=person_id),
            with_description,
        )


class AddToDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/AddToDepartmentResource_post.yml")
    def post(self, person_id):
        """
        Add person to department
        """
        permissions.check_admin_permissions()
        body = validation.validate_request_body(AddToDepartmentSchema)
        department_id = str(body.department_id)

        try:
            department = tasks_service.get_department(department_id)
        except DepartmentNotFoundException:
            raise WrongParameterException(
                "Department ID matches no department"
            )
        person = persons_service.add_to_department(department["id"], person_id)
        return person, 201


class RemoveFromDepartmentResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/RemoveFromDepartmentResource_delete.yml")
    def delete(self, person_id, department_id):
        """
        Remove person from department
        """
        permissions.check_admin_permissions()
        try:
            tasks_service.get_department(department_id)
        except DepartmentNotFoundException:
            raise WrongParameterException(
                "Department ID matches no department"
            )
        persons_service.remove_from_department(department_id, person_id)
        return "", 204


class ChangePasswordForPersonResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from("openapi/ChangePasswordForPersonResource_post.yml")
    def post(self, person_id):
        """
        Change person password
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        body = validation.validate_request_body(ChangePasswordSchema)
        password, password_2 = body.password, body.password_2
        current_user = persons_service.get_current_user()
        try:
            person = persons_service.check_password_change_allowed(person_id)
            auth.validate_password(password, password_2)
            password = auth.encrypt_password(password)
            persons_service.update_password(person["email"], password)
            current_app.logger.warning(
                f'User {current_user["email"]} has changed the password of {person["email"]}'
            )
            person_IP = request.headers.get("X-Forwarded-For", None)
            if person_IP:
                try:
                    ipaddress.ip_address(person_IP.split(",")[0].strip())
                    person_IP = person_IP.split(",")[0].strip()
                except ValueError:
                    person_IP = None
            persons_service.send_password_changed_by_admin_email(
                person, current_user, person_IP=person_IP
            )
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
        except InactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except PersonInProtectedAccounts as exception:
            return (
                {
                    "error": True,
                    "message": exception.description,
                },
                400,
            )


class DisableTwoFactorAuthenticationPersonResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(
        "openapi/DisableTwoFactorAuthenticationPersonResource_delete.yml"
    )
    def delete(self, person_id):
        """
        Disable two factor authentication
        """
        permissions_service.check_person_is_not_bot(person_id)
        permissions.check_admin_permissions()
        current_user = persons_service.get_current_user()
        try:
            person = persons_service.get_person(person_id)
            if (
                person["role"] == "admin"
                and person["id"] != current_user["id"]
            ):
                return {
                    "error": True,
                    "message": "An admin can't disable 2FA for other admins.",
                }, 400
            disable_two_factor_authentication_for_person(person["id"])
            current_app.logger.warning(
                f'User {current_user["email"]} has disabled the two factor authentication of {person["email"]}'
            )
            person_IP = request.headers.get("X-Forwarded-For", None)
            if person_IP:
                try:
                    ipaddress.ip_address(person_IP.split(",")[0].strip())
                    person_IP = person_IP.split(",")[0].strip()
                except ValueError:
                    person_IP = None
            persons_service.send_2fa_disabled_by_admin_email(
                person, current_user, person_IP=person_IP
            )
            return {"success": True}

        except InactiveUserException:
            return {"error": True, "message": "User is unactive."}, 400
        except TwoFactorAuthenticationNotEnabledException:
            return {
                "error": True,
                "message": "Two factor authentication not enabled for this user.",
            }, 400


class ClearAvatarPersonResource(MethodView):
    @jwt_required()
    @swag_from("openapi/ClearAvatarPersonResource_delete.yml")
    def delete(self, person_id):
        """
        Clear person avatar
        """
        permissions.check_admin_permissions()
        persons_service.clear_avatar(person_id)
        return "", 204
