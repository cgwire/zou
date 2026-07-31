from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, permissions

from zou.app.services import events_service, user_service
from zou.app.services.exception import (
    ProjectNotFoundException,
    WrongParameterException,
)


class EventsResource(MethodView, ArgsMixin):
    @jwt_required()
    def get(self):
        """
        Get events
        ---
        description: Retrieve last events with filtering support. Filters can be
          specified in the query string to narrow down results by date range,
          project, or other criteria.
        tags:
          - Events
        parameters:
          - in: query
            name: after
            type: string
            format: date
            example: "2022-07-12"
            description: Filter events after this date
          - in: query
            name: before
            type: string
            format: date
            example: "2022-07-12"
            description: Filter events before this date
          - in: query
            name: only_files
            type: boolean
            default: false
            description: Return only file-related events
            example: false
          - in: query
            name: cursor_event_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: ID of the last event from previous page for cursor-based pagination
          - in: query
            name: limit
            type: integer
            default: 100
            example: 100
            description: Maximum number of events to return
          - in: query
            name: project_id
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Filter events by specific project
          - in: query
            name: name
            type: string
            example: "user_login"
            description: Filter events by event name
          - in: query
            name: name_prefixes
            type: array
            items:
              type: string
            example: ["task", "comment"]
            description: Filter events by object, the part of the event name
              before the colon. Repeat the parameter for each value.
          - in: query
            name: name_suffixes
            type: array
            items:
              type: string
            example: ["update", "delete"]
            description: Filter events by action, the part of the event name
              after the colon. Repeat the parameter for each value.
          - in: query
            name: person_ids
            type: array
            items:
              type: string
              format: uuid
            description: Filter events by author. Repeat the parameter for
              each value.
        responses:
          200:
            description: List of events successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Event unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        description: Event name
                        example: "user_login"
                      data:
                        type: object
                        description: Event data content
                        example: {"user_id": "b35b7fb5-df86-5776-b181-68564193d36"}
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Event timestamp
                        example: "2023-01-01T12:00:00Z"
                      user_id:
                        type: string
                        format: uuid
                        description: User identifier who triggered the event
                        example: d57d9hd7-fh08-7998-d403-80786315f58
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
                user_service.resolve_project_role(project_id)
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
    def get(self):
        """
        Get login logs
        ---
        description: Retrieve last login logs with filtering support. Filters can
          be specified in the query string to narrow down results by date range
          or cursor-based pagination.
        tags:
          - Events
        parameters:
          - in: query
            name: after
            type: string
            format: date
            example: "2022-07-12"
            description: Filter logs after this date
          - in: query
            name: before
            type: string
            format: date
            example: "2022-07-12"
            description: Filter logs before this date
          - in: query
            name: cursor_login_log_id
            required: False
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: ID of the last login log from previous page for cursor-based pagination
          - in: query
            name: limit
            type: integer
            default: 100
            example: 100
            description: Maximum number of login logs to return
          - in: query
            name: person_ids
            type: array
            items:
              type: string
              format: uuid
            description: Filter login logs by person. Repeat the parameter for
              each value.
        responses:
          200:
            description: List of login logs successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Login log unique identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      created_at:
                        type: string
                        format: date-time
                        description: Login timestamp
                        example: "2023-01-01T12:00:00Z"
                      ip_address:
                        type: string
                        description: IP address of the login
                        example: "192.168.1.100"
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      origin:
                        type: string
                        description: Login origin
                        example: "web"
                        enum: ["web", "script"]
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
    def get(self):
        """
        Get event names
        ---
        description: Retrieve the distinct event names present in the log. It
          is meant to build the object and action filters of the log screen.
          The list is not scoped to the caller's productions: it exposes the
          event vocabulary, not any production data.
        tags:
          - Events
        responses:
          200:
            description: Sorted list of the event names in use
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: string
                    example: "task:update"
        """
        permissions.check_manager_permissions()
        return events_service.get_event_names()
