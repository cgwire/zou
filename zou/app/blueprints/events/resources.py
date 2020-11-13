from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import fields, permissions

from zou.app.services import events_service
from zou.app.services.exception import WrongParameterException


class EventsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self):
        args = self.get_args([
            ("after", None, False),
            ("before", None, False),
            ("only_files", False, False),
            ("page_size", 100, False),
            ("project_id", None, False),
        ])
        permissions.check_manager_permissions()
        before = self.parse_date_parameter(args["before"])
        after = self.parse_date_parameter(args["after"])
        page_size = args["page_size"]
        only_files = args["only_files"] == "true"
        project_id = args.get("project_id", None)
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
                project_id=project_id
            )


class LoginLogsResource(Resource, ArgsMixin):
    @jwt_required
    def get(self):
        args = self.get_args(
            [("before", None, None), ("page_size", 100, False)]
        )
        permissions.check_manager_permissions()
        before = None
        if args["before"] is not None:
            before = fields.get_date_object(args["before"], "%Y-%m-%dT%H:%M:%S")
        page_size = args["page_size"]
        return events_service.get_last_login_logs(before, page_size)
