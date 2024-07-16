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
        Retrieve last events.
        ---
        tags:
          - Events
        parameters:
          - in: query
            name: after
            type: string
            format: date
            x-example: "2022-07-12"
          - in: query
            name: before
            type: string
            format: date
            x-example: "2022-07-12"
          - in: query
            name: only_files
            type: boolean
            default: False
          - in: query
            name: page_size
            type: integer
            default: 100
            x-example: 100
          - in: query
            name: project_id
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All login logs
        """
        args = self.get_args(
            [
                ("after", None, False),
                ("before", None, False),
                ("only_files", False, False),
                ("page_size", 100, False),
                ("project_id", None, False),
                ("name", None, False),
            ],
        )

        permissions.check_manager_permissions()
        before = self.parse_date_parameter(args["before"])
        after = self.parse_date_parameter(args["after"])
        page_size = args["page_size"]
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
                page_size=page_size,
                only_files=only_files,
                project_id=project_id,
                name=name,
            )


class LoginLogsResource(Resource, ArgsMixin):
    @jwt_required()
    def get(self):
        """
        Retrieve all login logs.
        ---
        tags:
          - Events
        parameters:
          - in: query
            name: before
            type: string
            format: date
            x-example: "2022-07-12T00:00:00"
          - in: query
            name: page_size
            type: integer
            x-example: 100
        responses:
            200:
                description: All login logs
        """
        args = self.get_args(["before", ("page_size", 100)])

        permissions.check_manager_permissions()
        before = None
        if args["before"] is not None:
            before = date_helpers.get_datetime_from_string(args["before"])
        page_size = args["page_size"]
        return events_service.get_last_login_logs(before, page_size)
