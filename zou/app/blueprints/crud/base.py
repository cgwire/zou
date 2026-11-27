"""
Generic CRUD resources shared by every model exposed under /data.

BaseModelsResource handles the collection (GET list, POST create).
BaseModelResource handles the single instance (GET, PUT, DELETE). The
subclasses of each model in this package change the behavior through
hooks. They do not write the HTTP methods again:

- check_read_permissions / check_create_permissions(data) /
  check_update_permissions(instance, data) / check_delete_permissions
  (instance): raise permissions.PermissionDenied to refuse the request.
  By default, only an admin has access.
- add_project_permission_filter(query): limit a list query to the
  projects that the caller can see.
- update_data(data[, instance_id]): clean or complete the payload before
  the model gets it. The base method removes the protected fields. On
  update, it also validates the dates. Overrides call it first.
- pre/post_create, pre/post_update, pre/post_delete: side effects before
  and after the mutation. The emit_*_event methods emit the events.

Hooks run inside the request. If a hook raises a domain exception, the
matching error handler answers. This module catches the integrity and
statement errors and returns them as sanitized 400 responses (see
build_db_error_message).
"""

import datetime
import math

import orjson as json
import sqlalchemy.orm as orm
from flask import current_app, request
from flask.views import MethodView
from flask_jwt_extended import jwt_required
from sqlalchemy import types as sa_types
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.inspection import inspect

from zou.app.exceptions import (
    WrongParameterException,
)
from zou.app.mixin import ArgsMixin
from zou.app.utils import events, fields, permissions, query
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/base.yml")

UNIQUE_VIOLATION_MESSAGE = (
    "A record with the same unique values already exists."
)


def build_db_error_message(exception):
    """
    Return a message about the database error that is safe for the client.
    The raw text of the exception contains SQL statements and bound
    parameter values. These must stay in the server logs and never reach
    the client.
    """
    if isinstance(exception, IntegrityError):
        origin = str(getattr(exception, "orig", exception)).lower()
        if "duplicate key" in origin or "unique constraint" in origin:
            return UNIQUE_VIOLATION_MESSAGE
        if "foreign key" in origin:
            return "The change conflicts with records referencing this one."
        if "not-null" in origin or "null value" in origin:
            return "A required field is missing."
        return "The data conflicts with database integrity rules."
    if isinstance(exception, StatementError):
        return "One of the provided values has an invalid format."
    return str(exception)


class BaseModelsResource(MethodView, ArgsMixin):
    def __init__(self, model):
        MethodView.__init__(self)
        self.model = model
        self.protected_fields = ["id", "created_at", "updated_at"]

    def get_relations_eager_load(self):
        """
        Return a list of relationship attributes to selectinload when the
        client sends ?relations=true. Subclasses override this for models
        that have collection relationships without lazy="selectin" on the
        model. Thus the bulk list endpoint does not do N+1 queries.
        """
        return []

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        if relations:
            for relationship in self.get_relations_eager_load():
                query = query.options(orm.selectinload(relationship))

        return self.serialize_list(query.all(), relations=relations)

    def serialize_list(self, entries, relations=False):
        return self.model.serialize_list(entries, relations=relations)

    def cursor_entries(self, db_query, cursor_id, limit, relations=False):
        return self.all_entries(
            query.apply_cursor(db_query, cursor_id, limit), relations=relations
        )

    def paginated_entries(self, query, page, limit=None, relations=False):
        total = query.count()
        limit = limit or current_app.config["NB_RECORDS_PER_PAGE"]
        if limit < 1:
            raise WrongParameterException("limit must be a positive integer.")
        offset = (page - 1) * limit

        nb_pages = int(math.ceil(total / float(limit)))
        query = query.order_by(
            self.model.updated_at.desc(),
            self.model.created_at.desc(),
            self.model.id,
        )
        query = query.limit(limit)
        query = query.offset(offset)

        if (total < offset) or (page < 1):
            result = {
                "data": [],
                "total": total,
                "nb_pages": nb_pages,
                "limit": limit,
                "offset": offset,
                "page": page,
            }
        else:
            result = {
                "data": self.all_entries(query=query, relations=relations),
                "total": total,
                "nb_pages": nb_pages,
                "limit": limit,
                "offset": offset,
                "page": page,
            }
        return result

    def get_filterable_column_names(self):
        """
        Return the names that the query filters accept. Filters run before
        serialization. Thus, if a column is not removed here, a client can
        filter on it by equality, also when the response hides it.
        Subclasses that return fewer columns must also return fewer names
        here.
        """
        return inspect(self.model).all_orm_descriptors.keys()

    def build_filters(self, options):
        many_join_filter = []
        in_filter = []
        name_filter = []
        filters = {}

        column_names = self.get_filterable_column_names()
        model_column_names = inspect(self.model).all_orm_descriptors.keys()
        for key, value in options.items():
            if key in ["page", "relations", "fields"]:
                continue

            if key not in column_names:
                # Refuse a column that is not in the filter set. Do not
                # ignore it: the query then answers a wider question than
                # the request. A client that reads the first row as the
                # match (gazu's fetch_first) then gets a random record, not
                # an error. Names that are not columns stay ignored,
                # because resources read their own parameters.
                if key in model_column_names:
                    raise WrongParameterException(
                        f"Filtering on {key} is not allowed."
                    )
            else:
                field_key = getattr(self.model, key)

                is_many_to_many_field = hasattr(
                    field_key, "property"
                ) and isinstance(
                    field_key.property, orm.properties.RelationshipProperty
                )
                value_is_list = (
                    hasattr(value, "__len__")
                    and len(value) > 0
                    and value[0] == "["
                )

                if key == "name" and field_key is not None:
                    name_filter.append(value)

                elif is_many_to_many_field:
                    many_join_filter.append((key, value))

                elif value_is_list:
                    try:
                        value_array = json.loads(value)
                    except ValueError:
                        raise WrongParameterException(
                            f"Malformed list filter for field {key}."
                        )
                    in_filter.append(
                        field_key.in_(
                            [
                                query.cast_value(value, field_key)
                                for value in value_array
                            ]
                        )
                    )
                else:
                    filters[key] = query.cast_value(value, field_key)

        return (many_join_filter, in_filter, name_filter, filters)

    def apply_filters(self, query, options):
        (
            many_join_filter,
            in_filter,
            name_filter,
            criterions,
        ) = self.build_filters(options)

        query = query.filter_by(**criterions)

        for value in name_filter:
            query = query.filter(self.model.name.ilike(value))

        for id_filter in in_filter:
            query = query.filter(id_filter)

        for key, value in many_join_filter:
            query = query.filter(getattr(self.model, key).any(id=value))

        return query

    def check_read_permissions(self, options=None):
        return permissions.check_admin_permissions()

    def add_project_permission_filter(self, query):
        return query

    def check_create_permissions(self, data):
        return permissions.check_admin_permissions()

    def check_creation_integrity(self, data):
        return data

    def update_data(self, data):
        for field in self.protected_fields:
            if (data is not None) and field in data:
                data.pop(field, None)
        return data

    def post_creation(self, instance):
        return instance.serialize(relations=True)

    @jwt_required()
    @swag_from(SPECS["BaseModelsResource_get"])
    def get(self):
        """
        Get models
        """
        try:
            query = self.model.query
            if not request.args:
                self.check_read_permissions()
                query = self.add_project_permission_filter(query)
                return self.all_entries(query)
            else:
                options = request.args
                self.check_read_permissions(options)
                query = self.apply_filters(query, options)
                query = self.add_project_permission_filter(query)
                page = self.get_page()
                limit = self.get_limit()
                cursor_id = self.get_cursor_id()
                relations = self.get_bool_parameter("relations")
                field_names = self.get_text_parameter("fields")
                if field_names:
                    field_names = [
                        name.strip() for name in field_names.split(",")
                    ]
                is_paginated = page > -1

                if is_paginated:
                    result = self.paginated_entries(
                        query, page, limit=limit, relations=relations
                    )
                    if field_names:
                        result["data"] = fields.pick_fields(
                            result["data"], field_names
                        )
                    return result
                else:
                    if limit or cursor_id:
                        result = self.cursor_entries(
                            query, cursor_id, limit, relations=relations
                        )
                    else:
                        result = self.all_entries(query, relations=relations)
                    if field_names:
                        result = fields.pick_fields(result, field_names)
                    return result
        except StatementError as exception:
            # If the driver refuses a filter value (a word for an int
            # column, a malformed date), the error occurs here, on
            # execution. The raw text contains the statement and its bound
            # values. Thus only the sanitized message goes to the client.
            current_app.logger.info(str(exception))
            return (
                {
                    "error": True,
                    "message": build_db_error_message(exception),
                },
                400,
            )
        except permissions.PermissionDenied:
            raise

    @jwt_required()
    @swag_from(SPECS["BaseModelsResource_post"])
    def post(self):
        """
        Create model
        """
        try:
            data = request.json
            if data is None:
                raise WrongParameterException(
                    "Data are empty. Please verify that you sent JSON data and"
                    " that you set the right headers."
                )
            self.check_create_permissions(data)
            self.check_creation_integrity(data)
            data = self.update_data(data)
            instance = self.model.create(**data)
            instance_dict = self.post_creation(instance)
            self.emit_create_event(instance_dict)
            return instance_dict, 201

        except (
            TypeError,
            IntegrityError,
            StatementError,
            KeyError,
        ) as exception:
            current_app.logger.warning(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

    def emit_create_event(self, instance_dict):
        return events.emit(
            f"{self.model.__tablename__.replace('_', '-')}:new",
            {f"{self.model.__tablename__}_id": instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )


class BaseModelResource(MethodView, ArgsMixin):
    def __init__(self, model):
        MethodView.__init__(self)
        self.protected_fields = ["id", "created_at", "updated_at"]
        if "project_id" in model.__table__.columns:
            # check_update_permissions validates the project of the stored
            # instance, never the project of the body. Without this, a
            # payload with another project_id moved the row into a
            # production that the check did not examine. This does not
            # change creation: BaseModelsResource needs the project.
            self.protected_fields.append("project_id")
        self.model = model
        self.instance = None

    def get_model_or_404(self, instance_id):
        if not fields.is_valid_id(instance_id):
            raise WrongParameterException("Malformed ID.")
        from werkzeug.exceptions import NotFound

        instance = self.model.get(instance_id)
        if instance is None:
            raise NotFound
        return instance

    def get_serialized_instance(self, instance_id, relations=True):
        instance = self.get_model_or_404(instance_id)
        return self.serialize_instance(instance, relations=relations)

    def check_read_permissions(self, instance_dict):
        return permissions.check_admin_permissions()

    def check_update_permissions(self, instance_dict, data):
        return permissions.check_admin_permissions()

    def check_delete_permissions(self, instance_dict):
        return permissions.check_admin_permissions()

    def get_arguments(self):
        return request.json

    def update_data(self, data, instance_id):
        for field in self.protected_fields:
            if (data is not None) and field in data:
                data.pop(field, None)
        self._validate_date_fields(data)
        return data

    def _validate_date_fields(self, data):
        """
        Make sure that the parser can read each incoming string for a Date
        or DateTime column. If it cannot, raise WrongParameterException
        with a clear message. Thus a malformed value like ``"2026-04-"``
        does not cause a crash in PostgreSQL.
        """
        if data is None:
            return
        columns = {
            col.name: col
            for col in self.model.__table__.columns
            if isinstance(col.type, (sa_types.DateTime, sa_types.Date))
        }
        for key, value in data.items():
            if key in columns and isinstance(value, str) and value != "":
                try:
                    # fromisoformat accepts the ISO 8601 values that
                    # PostgreSQL accepts (date only, time offsets...), but
                    # not a Z after a date only (2026-04-01Z). Thus, change
                    # Z to +00:00.
                    datetime.datetime.fromisoformat(
                        value.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise WrongParameterException(
                        f"Invalid date format for '{key}': '{value}'. "
                        "Expected an ISO 8601 date or datetime."
                    )

    def serialize_instance(self, data, relations=True):
        return data.serialize(relations=relations)

    def serialize_update_response(self, instance):
        return instance.serialize()

    def clean_get_result(self, data):
        return data

    @jwt_required()
    @swag_from(SPECS["BaseModelResource_get"])
    def get(self, instance_id):
        """
        Get model
        """
        relations = self.get_bool_parameter("relations", "true")
        try:
            result = self.get_serialized_instance(
                instance_id, relations=relations
            )
            self.check_read_permissions(result)
            result = self.clean_get_result(result)

        except StatementError as exception:
            current_app.logger.warning(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

        except ValueError:
            raise WrongParameterException("Invalid value.")

        return result, 200

    def pre_update(self, instance_dict, data):
        return data

    def post_update(self, instance_dict, data):
        return instance_dict

    def post_delete(self, instance_dict):
        return instance_dict

    def pre_delete(self, instance_dict):
        return instance_dict

    @jwt_required()
    @swag_from(SPECS["BaseModelResource_put"])
    def put(self, instance_id):
        """
        Update model
        """
        try:
            data = self.get_arguments()
            if data is None:
                raise WrongParameterException(
                    "Data are empty. Please verify that you sent JSON data and"
                    " that you set the right headers."
                )
            self.instance = self.get_model_or_404(instance_id)
            instance_dict = self.instance.serialize()
            self.check_update_permissions(instance_dict, data)
            self.pre_update(instance_dict, data)
            data = self.update_data(data, instance_id)
            self.instance.update(data)
            instance_dict = self.serialize_update_response(self.instance)
            self.post_update(instance_dict, data)
            self.emit_update_event(instance_dict)
            return instance_dict, 200

        except (
            TypeError,
            IntegrityError,
            StatementError,
        ) as exception:
            current_app.logger.warning(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

    @jwt_required()
    @swag_from(SPECS["BaseModelResource_delete"])
    def delete(self, instance_id):
        """
        Delete model
        """
        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            instance.delete()
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except (IntegrityError, StatementError) as exception:
            current_app.logger.warning(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

        return "", 204

    def emit_update_event(self, instance_dict):
        return events.emit(
            f"{self.model.__tablename__.replace('_', '-')}:update",
            {f"{self.model.__tablename__}_id": instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )

    def emit_delete_event(self, instance_dict):
        return events.emit(
            f"{self.model.__tablename__.replace('_', '-')}:delete",
            {f"{self.model.__tablename__}_id": instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )
