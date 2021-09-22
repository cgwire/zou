from flask_restful import reqparse
from flask import request

from zou.app.utils import fields
from zou.app.services.exception import WrongParameterException


class ArgsMixin(object):
    """
    Helpers to retrieve parameters from GET or POST queries.
    """

    def get_args(self, descriptors):
        parser = reqparse.RequestParser()
        for descriptor in descriptors:
            action = None
            data_type = str

            if len(descriptor) == 5:
                (name, default, required, action, type) = descriptor
            elif len(descriptor) == 4:
                (name, default, required, action) = descriptor
            else:
                (name, default, required) = descriptor

            parser.add_argument(
                name,
                required=required,
                default=default,
                action=action,
                type=data_type,
            )

        return parser.parse_args()

    def clear_empty_fields(self, data):
        """
        Remove fields set to None from data dict.
        """
        for key in list(data.keys()):
            if data[key] is None:
                del data[key]
        return data

    def get_page(self):
        """
        Returns page requested by the user.
        """
        options = request.args
        return int(options.get("page", "-1"))

    def get_sort_by(self):
        """
        Returns sort by option value
        """
        return self.get_text_parameter("sort_by")

    def get_force(self):
        """
        Returns force parameter.
        """
        return self.get_bool_parameter("force")

    def get_relations(self):
        """
        Returns force parameter.
        """
        return self.get_bool_parameter("relations")

    def get_project_id(self):
        """
        Returns episode ID parameter.
        """
        return self.get_text_parameter("project_id")

    def get_episode_id(self):
        """
        Returns episode ID parameter.
        """
        return self.get_text_parameter("episode_id")

    def get_no_job(self):
        """
        Returns no_job parameter.
        """
        return self.get_bool_parameter("no_job")

    def get_text_parameter(self, field_name):
        options = request.args
        return options.get(field_name, None)

    def get_bool_parameter(self, field_name):
        options = request.args
        return options.get(field_name, "false") == "true"

    def get_date_parameter(self, field_name):
        self.parse_date_parameter(self.get_text_parameter(field_name))

    def parse_date_parameter(self, param):
        date = None
        if param is None:
            return date
        try:
            date = fields.get_date_object(param, "%Y-%m-%dT%H:%M:%S")
        except Exception:
            try:
                date = fields.get_date_object(param, "%Y-%m-%d")
            except Exception:
                raise WrongParameterException(
                    "Wrong date format for before argument."
                    "Expected format: 2020-01-05T13:23:10 or 2020-01-05"
                )
        return date
