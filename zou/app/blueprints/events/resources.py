from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, permissions, date_helpers

from zou.app.services import events_service
from zou.app.services.exception import WrongParameterException


class EventsResource(Resource, ArgsMixin):
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
                ("limit", 100, False),
                ("project_id", None, False),
                ("name", None, False),
            ],
        )

        permissions.check_manager_permissions()
        before = self.parse_date_parameter(args["before"])
        after = self.parse_date_parameter(args["after"])
        limit = args["limit"]
        only_files = args["only_files"] == "true"
        project_id = args.get("project_id", None)
        name = args["name"]
        if project_id is not None and not fields.is_valid_id(project_id):
            raise WrongParameterException(
                "The project_id parameter is not a valid id"
            )
        else:
            return events_service.get_last_events(
                after=after,
                before=before,
                limit=limit,
                only_files=only_files,
                project_id=project_id,
                name=name,
            )


class LoginLogsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self):
        """
        Get login logs
        ---
        description: Retrieve all login logs with filtering support. Filters can
          be specified in the query string to narrow down results by date range
          and limit.
        tags:
          - Events
        parameters:
          - in: query
            name: before
            type: string
            format: date-time
            example: "2022-07-12T00:00:00"
            description: Filter logs before this date and time
          - in: query
            name: limit
            type: integer
            example: 100
            description: Maximum number of login logs to return
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
                      user_id:
                        type: string
                        format: uuid
                        description: User identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      ip_address:
                        type: string
                        description: IP address of the login
                        example: "192.168.1.100"
                      user_agent:
                        type: string
                        description: User agent string
                        example: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                      success:
                        type: boolean
                        description: Whether the login was successful
                        example: true
                      created_at:
                        type: string
                        format: date-time
                        description: Login timestamp
                        example: "2023-01-01T12:00:00Z"
        """
        args = self.get_args(["before", ("limit", 100)])

        permissions.check_manager_permissions()
        before = None
        if args["before"] is not None:
            before = date_helpers.get_datetime_from_string(args["before"])
        limit = args["limit"]
        return events_service.get_last_login_logs(before, limit)
