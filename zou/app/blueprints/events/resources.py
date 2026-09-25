from flasgger import swag_from
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, permissions

from zou.app.services import events_service, permissions_service, user_service
from zou.app.exceptions import (
    ProjectNotFoundException,
    WrongParameterException,
)


class EventsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/EventsResource_get.yml")
    def get(self):
        """
        Get events
        """
        args = self.get_args(
            [
                ("after", None, False),
                ("before", None, False),
                ("only_files", False, False),
                ("cursor_event_id", None, False),
                ("limit", 100, False, int),
                ("project_id", None, False),
                ("name", None, False),
                ("name_prefixes", [], False, str, "append"),
                ("name_suffixes", [], False, str, "append"),
                ("person_ids", [], False, str, "append"),
            ],
        )

        project_id = args.get("project_id", None)
        if project_id is not None and not fields.is_valid_id(project_id):
            raise WrongParameterException(
                "The project_id parameter is not a valid id"
            )

        # A manager role can be held per production, so resolve it before the
        # role check reads it, otherwise the global role silently wins. An
        # unknown project is reported as a denial rather than a 404: the
        # caller has no right to learn whether it exists. The check stays
        # ahead of every other parameter so an unauthorized caller never
        # gets a validation error instead of a denial.
        if (
            project_id is not None
            and not permissions.has_manager_permissions()
        ):
            try:
                permissions_service.resolve_project_role(project_id)
            except ProjectNotFoundException:
                raise permissions.PermissionDenied
        permissions.check_manager_permissions()

        before = self.parse_date_parameter(args["before"])
        after = self.parse_date_parameter(args["after"])
        cursor_event_id = args["cursor_event_id"]
        limit = min(args["limit"], 1000)
        only_files = args["only_files"] == "true"
        name = args["name"]
        if cursor_event_id is not None and not fields.is_valid_id(
            cursor_event_id
        ):
            raise WrongParameterException(
                "The cursor_event_id parameter is not a valid id"
            )

        # Admins read the whole log. Managers are scoped to the productions
        # they belong to, which also hides the events carrying no project at
        # all (persons, organisation, settings).
        project_ids = None
        if not permissions.has_admin_permissions():
            project_ids = [
                project["id"] for project in user_service.get_projects()
            ]
            if project_id is not None and project_id not in project_ids:
                raise permissions.PermissionDenied

        return events_service.get_last_events(
            after=after,
            before=before,
            cursor_event_id=cursor_event_id,
            limit=limit,
            only_files=only_files,
            project_id=project_id,
            project_ids=project_ids,
            name=name,
            name_prefixes=args["name_prefixes"],
            name_suffixes=args["name_suffixes"],
            person_ids=args["person_ids"],
        )


class LoginLogsResource(MethodView, ArgsMixin):
    @jwt_required()
    @swag_from("openapi/LoginLogsResource_get.yml")
    def get(self):
        """
        Get login logs
        """
        args = self.get_args(
            [
                ("after", None, False),
                ("before", None, False),
                ("cursor_login_log_id", None, False),
                ("limit", 100, False, int),
                ("person_ids", [], False, str, "append"),
            ],
        )

        # Login logs carry the IP address of every person and cover the whole
        # studio, with no production to scope them on: admins only.
        permissions.check_admin_permissions()
        before = self.parse_date_parameter(args["before"])
        after = self.parse_date_parameter(args["after"])
        cursor_login_log_id = args["cursor_login_log_id"]
        limit = min(args["limit"], 1000)
        if cursor_login_log_id is not None and not fields.is_valid_id(
            cursor_login_log_id
        ):
            raise WrongParameterException(
                "The cursor_login_log_id parameter is not a valid id"
            )
        return events_service.get_last_login_logs(
            after=after,
            before=before,
            cursor_login_log_id=cursor_login_log_id,
            limit=limit,
            person_ids=args["person_ids"],
        )


class EventNamesResource(MethodView):
    @jwt_required()
    @swag_from("openapi/EventNamesResource_get.yml")
    def get(self):
        """
        Get event names
        """
        permissions.check_manager_permissions()
        return events_service.get_event_names()
