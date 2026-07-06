from flask import request

from zou.app.utils import date_helpers, fields
from zou.app.services.exception import WrongParameterException


class ArgsMixin(object):
    """
    Helpers to retrieve parameters from GET or POST queries.
    """

    def get_args(self, descriptors, location=None):
        """
        Retrieve arguments from GET or POST queries.
        """
        if location is None:
            location = ["values", "json"] if request.is_json else ["values"]
        elif isinstance(location, str):
            location = [location]

        sources = []
        for source_name in location:
            if source_name == "json":
                json_body = request.get_json(silent=True)
                if isinstance(json_body, dict):
                    sources.append(json_body)
            else:
                sources.append(getattr(request, source_name))

        args = {}
        for descriptor in descriptors:
            action = None
            data_type = str
            required = False
            default = None

            if isinstance(descriptor, (list, tuple)):
                if len(descriptor) == 5:
                    name, default, required, data_type, action = descriptor
                elif len(descriptor) == 4:
                    name, default, required, data_type = descriptor
                elif len(descriptor) == 3:
                    name, default, required = descriptor
                elif len(descriptor) == 2:
                    name, default = descriptor
                elif len(descriptor) == 1:
                    name = descriptor
                else:
                    raise ValueError
            elif isinstance(descriptor, str):
                name = descriptor
            elif isinstance(descriptor, dict):
                name = descriptor.get("name")
                required = descriptor.get("required", required)
                default = descriptor.get("default", default)
                action = descriptor.get("action", action)
                data_type = descriptor.get("type", data_type)

            args[name] = self._parse_arg(
                sources, name, default, required, data_type, action
            )
        return args

    @staticmethod
    def _parse_arg(sources, name, default, required, data_type, action):
        """
        Resolve a single argument against the request sources: first source
        holding the name wins, values are cast with data_type, and
        action="append" collects every occurrence as a list.
        """
        source = next((s for s in sources if name in s), None)
        if source is None:
            if required:
                raise WrongParameterException(
                    f"Missing required parameter: {name}"
                )
            return default

        def convert(value):
            if value is None or data_type is None:
                return value
            try:
                return data_type(value)
            except (TypeError, ValueError):
                raise WrongParameterException(
                    f"Wrong value for parameter {name}."
                )

        if action == "append":
            if hasattr(source, "getlist"):
                values = source.getlist(name)
            else:
                values = source[name]
                if not isinstance(values, list):
                    values = [values]
            return [convert(value) for value in values]

        return convert(source.get(name))

    def clear_empty_fields(self, data, ignored_fields=None):
        """
        Remove fields set to None from data dict.
        """
        if ignored_fields is None:
            ignored_fields = []
        for key in list(data.keys()):
            if key not in ignored_fields and data[key] is None:
                del data[key]
        return data

    def get_page(self):
        """
        Returns page requested by the user as an integer.
        """
        return self.get_integer_parameter("page", -1)

    def get_limit(self):
        """
        Returns limit requested by the user as an integer.
        """
        return self.get_integer_parameter("limit", 0)

    def get_integer_parameter(self, field_name, default=0):
        """
        Returns an integer query parameter, raising a 400 error when the
        value is not a valid integer.
        """
        try:
            return int(request.args.get(field_name, default))
        except ValueError:
            raise WrongParameterException(f"{field_name} must be an integer.")

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
        Returns relations parameter.
        """
        return self.get_bool_parameter("relations")

    def get_project_id(self):
        """
        Returns project ID parameter.
        """
        return self.get_text_parameter("project_id")

    def get_episode_id(self):
        """
        Returns episode ID parameter.
        """
        return self.get_text_parameter("episode_id")

    def get_task_type_id(self):
        """
        Returns Task type ID parameter.
        """
        return self.get_text_parameter("task_type_id")

    def get_no_job(self):
        """
        Returns no_job parameter.
        """
        return self.get_bool_parameter("no_job")

    def get_text_parameter(self, field_name, default=None):
        """
        Returns text parameter value matching `field_name`.
        """
        options = request.args
        return options.get(field_name, default)

    def get_bool_parameter(self, field_name, default="false"):
        """
        Returns bool parameter value matching `field_name`.
        """
        options = request.args
        return options.get(field_name, default).lower() == "true"

    def get_date_parameter(self, field_name):
        """
        Returns date parameter value matching `field_name`.
        """
        return self.parse_date_parameter(self.get_text_parameter(field_name))

    def parse_date_parameter(self, param):
        date = None
        if param is None:
            return date
        try:
            date = date_helpers.get_datetime_from_string(param)
        except Exception:
            try:
                date = date_helpers.get_date_from_string(param)
            except Exception:
                raise WrongParameterException(
                    "Wrong date format for before argument."
                    "Expected format: 2020-01-05T13:23:10 or 2020-01-05"
                )
        return date

    def check_id_parameter(self, uuid):
        """
        Check if the given UUID is valid.
        """
        if not fields.is_valid_id(uuid):
            raise WrongParameterException("Wrong UUID format.")
        return True

    def get_id_parameter(self, field_name, default=None):
        """
        Returns ID parameter value matching `field_name`.
        """
        entity_id = self.get_text_parameter(field_name + "_id", default)
        if entity_id is not None and entity_id != "":
            self.check_id_parameter(entity_id)
        return entity_id
