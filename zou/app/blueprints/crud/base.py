import math
import orjson as json
import sqlalchemy.orm as orm

from flask import request, abort, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.inspection import inspect

from zou.app.mixin import ArgsMixin
from zou.app.utils import events, fields, permissions, query
from zou.app.services.exception import (
    WrongParameterException,
)


class BaseModelsResource(Resource, ArgsMixin):
    def __init__(self, model):
        Resource.__init__(self)
        self.model = model
        self.protected_fields = ["id", "created_at", "updated_at"]

    def all_entries(self, query=None, relations=False):
        if query is None:
            query = self.model.query

        return self.serialize_list(query.all(), relations=relations)

    def serialize_list(self, entries, relations=False):
        return self.model.serialize_list(entries, relations=relations)

    def paginated_entries(self, query, page, limit=None, relations=False):
        total = query.count()
        limit = limit or current_app.config["NB_RECORDS_PER_PAGE"]
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
                "total": 0,
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

    def build_filters(self, options):
        many_join_filter = []
        in_filter = []
        name_filter = []
        filters = {}

        column_names = inspect(self.model).all_orm_descriptors.keys()
        for key, value in options.items():
            if key not in ["page", "relations"] and key in column_names:
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
                    value_array = json.loads(value)
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
        return instance.serialize()

    @jwt_required()
    def get(self):
        """
        Get models
        ---
        tags:
          - Crud
        description: Retrieve all entries for the given model. Supports
          filtering via query parameters and pagination.
        parameters:
          - in: query
            name: page
            required: false
            schema:
              type: integer
            example: 1
            description: Page number for pagination
          - in: query
            name: limit
            required: false
            schema:
              type: integer
            example: 50
            description: Number of results per page
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: false
            example: false
            description: Whether to include relations
        responses:
            200:
              description: Models retrieved successfully
              content:
                application/json:
                  schema:
                    oneOf:
                      - type: array
                        items:
                          type: object
                      - type: object
                        properties:
                          data:
                            type: array
                            items:
                              type: object
                            example: []
                          total:
                            type: integer
                            example: 100
                          nb_pages:
                            type: integer
                            example: 2
                          limit:
                            type: integer
                            example: 50
                          offset:
                            type: integer
                            example: 0
                          page:
                            type: integer
                            example: 1
            400:
              description: Invalid filter format or query error
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
                page = int(options.get("page", "-1"))
                limit = int(options.get("limit", 0))
                relations = self.get_bool_parameter("relations")
                is_paginated = page > -1

                if is_paginated:
                    return self.paginated_entries(
                        query, page, limit=limit, relations=relations
                    )
                else:
                    return self.all_entries(query, relations=relations)
        except StatementError as exception:
            if hasattr(exception, "message"):
                return (
                    {
                        "error": True,
                        "message": "One of the value of the filter has not the"
                        " proper format: %s" % exception.message,
                    },
                    400,
                )
            else:
                raise exception
        except permissions.PermissionDenied:
            abort(403)

    @jwt_required()
    def post(self):
        """
        Create model
        ---
        tags:
          - Crud
        description: Create a new model instance with data provided in the
          request body. JSON format is expected. The model performs validation
          automatically when instantiated.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: Model Name
        responses:
            201:
              description: Model created successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Model Name
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid data format or validation error
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
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

    def emit_create_event(self, instance_dict):
        return events.emit(
            "%s:new" % self.model.__tablename__.replace("_", "-"),
            {"%s_id" % self.model.__tablename__: instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )


class BaseModelResource(Resource, ArgsMixin):
    def __init__(self, model):
        Resource.__init__(self)
        self.protected_fields = ["id", "created_at", "updated_at"]
        self.model = model
        self.instance = None

    def get_model_or_404(self, instance_id):
        if not fields.is_valid_id(instance_id):
            raise WrongParameterException("Malformed ID.")
        instance = self.model.get(instance_id)
        if instance is None:
            abort(404)
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
        return data

    def serialize_instance(self, data, relations=True):
        return data.serialize(relations=relations)

    def clean_get_result(self, data):
        return data

    @jwt_required()
    def get(self, instance_id):
        """
        Get model
        ---
        tags:
          - Crud
        description: Retrieve a model instance by its ID and return it as a
          JSON object. Supports including relations.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: query
            name: relations
            required: false
            schema:
              type: boolean
            default: true
            example: true
            description: Whether to include relations
        responses:
            200:
              description: Model retrieved successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Model Name
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
            400:
              description: Invalid ID format or query error
        """
        relations = self.get_bool_parameter("relations", "true")
        try:
            result = self.get_serialized_instance(
                instance_id, relations=relations
            )
            self.check_read_permissions(result)
            result = self.clean_get_result(result)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            abort(404)

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
    def put(self, instance_id):
        """
        Update model
        ---
        tags:
          - Crud
        description: Update a model instance with data provided in the
          request body. JSON format is expected. Model performs validation
          automatically when fields are modified.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                properties:
                  name:
                    type: string
                    example: Updated Model Name
        responses:
            200:
              description: Model updated successfully
              content:
                application/json:
                  schema:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      name:
                        type: string
                        example: Updated Model Name
                      created_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T10:30:00Z"
                      updated_at:
                        type: string
                        format: date-time
                        example: "2024-01-15T11:00:00Z"
            400:
              description: Invalid data format or validation error
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
            instance_dict = self.instance.serialize()
            self.post_update(instance_dict, data)
            self.emit_update_event(instance_dict)
            return instance_dict, 200

        except (
            TypeError,
            IntegrityError,
            StatementError,
        ) as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete model
        ---
        tags:
          - Crud
        description: Delete a model instance by its ID. Returns empty
          response on success.
        parameters:
          - in: path
            name: instance_id
            required: true
            schema:
              type: string
              format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
              description: Model deleted successfully
            400:
              description: Integrity error or cannot delete
        """
        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            instance.delete()
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204

    def emit_update_event(self, instance_dict):
        return events.emit(
            "%s:update" % self.model.__tablename__.replace("_", "-"),
            {"%s_id" % self.model.__tablename__: instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )

    def emit_delete_event(self, instance_dict):
        return events.emit(
            "%s:delete" % self.model.__tablename__.replace("_", "-"),
            {"%s_id" % self.model.__tablename__: instance_dict["id"]},
            project_id=instance_dict.get("project_id", None),
        )
