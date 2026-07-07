import math
import uuid

import orjson as json
import sqlalchemy.orm as orm

from zou.app import config
from zou.app.utils import fields, string
from zou.app.services.exception import WrongParameterException
from sqlalchemy import func
from sqlalchemy.inspection import inspect


def get_query_criterions_from_request(request):
    """
    Turn request parameters into a dict where keys are attributes to filter and
    values are values to filter.
    """
    criterions = {}
    for key, value in request.args.items():
        if key not in ["page"]:
            criterions[key] = value
    return criterions


# Some criterions accept sentinel values that are not UUIDs (e.g. "all" or
# "main" for episode_id) and must therefore bypass UUID validation.
EPISODE_ID_SENTINELS = ["all", "main"]


def check_criterion_id_format(
    criterions, id_fields=("id", "project_id", "episode_id")
):
    """
    Ensure the id criterions extracted from a request hold a valid UUID before
    they are injected into a custom SQL query. Resources that build queries by
    hand (the various "*-and-tasks" endpoints) bypass the casting done in
    apply_criterions_to_db_query, so an invalid UUID would otherwise reach the
    database and raise a StatementError (HTTP 500) instead of a 400.
    """
    for id_field in id_fields:
        value = criterions.get(id_field)
        if value is None:
            continue
        if id_field == "episode_id" and value in EPISODE_ID_SENTINELS:
            continue
        if not fields.is_valid_id(value):
            raise WrongParameterException(
                f"Invalid UUID format for {id_field}: {value}"
            )


def apply_criterions_to_db_query(model, db_query, criterions):
    """
    Apply criterions given in HTTP request to the sqlachemy db query object.
    """

    many_join_filter = []
    in_filter = []
    name_filter = []
    eq_filter = []

    column_names = inspect(model).all_orm_descriptors.keys()
    for key, value in criterions.items():
        if key not in ["page", "relations"] and key in column_names:
            field_key = getattr(model, key)

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
                        [cast_value(value, field_key) for value in value_array]
                    )
                )
            else:
                eq_filter.append(field_key == cast_value(value, field_key))

    for filter_clause in eq_filter:
        db_query = db_query.filter(filter_clause)

    for value in name_filter:
        db_query = db_query.filter(model.name.ilike(value))

    for id_filter in in_filter:
        db_query = db_query.filter(id_filter)

    for key, value in many_join_filter:
        db_query = db_query.filter(getattr(model, key).any(id=value))

    return db_query


def get_paginated_results(query, page, limit=None, relations=False):
    """
    Apply pagination to the query object.
    """
    if page < 1:
        entries = query.all()
        return fields.serialize_models(entries, relations=relations)
    else:
        limit = limit or config.NB_RECORDS_PER_PAGE
        total = query.count()
        offset = (page - 1) * limit

        nb_pages = int(math.ceil(total / float(limit)))
        query = query.limit(limit)
        query = query.offset(offset)

        if total < offset:
            result = {
                "data": [],
                "total": 0,
                "nb_pages": nb_pages,
                "limit": limit,
                "offset": offset,
                "page": page,
            }
        else:
            models = fields.serialize_models(query.all(), relations=relations)
            result = {
                "data": models,
                "total": total,
                "nb_pages": nb_pages,
                "limit": limit,
                "offset": offset,
                "page": page,
            }
        return result


def get_cursor_results(
    model,
    query,
    cursor_created_at,
    limit=None,
    relations=False,
):
    """ """
    limit = limit or config.NB_RECORDS_PER_PAGE
    total = query.count()
    query = (
        query.filter(model.created_at > cursor_created_at)
        .order_by(model.created_at, model.updated_at, model.id)
        .limit(limit)
    )
    models = fields.serialize_models(
        query.all(), relations=relations, milliseconds=True
    )
    result = {
        "data": models,
        "total": total,
        "limit": limit,
    }
    return result


def apply_sort_by(model, query, sort_by):
    """
    Apply an order by clause to a sqlalchemy query from a string parameter.
    """
    if sort_by in model.__table__.columns.keys():
        sort_field = model.__table__.columns[sort_by]
        if sort_by in ["created_at", "updated_at"]:
            sort_field = sort_field.desc()
    else:
        sort_field = model.updated_at.desc()
    return query.order_by(sort_field)


def cast_value(value, field_key):
    if field_key.type.python_type is bool:
        try:
            return string.strtobool(value)
        except ValueError:
            raise WrongParameterException(f"Invalid boolean value: {value}")
    elif field_key.type.python_type is uuid.UUID:
        if (
            value
            and not isinstance(value, uuid.UUID)
            and not fields.is_valid_id(value)
        ):
            raise WrongParameterException(f"Invalid UUID value: {value}")
        return func.cast(value, field_key.type)
    else:
        return func.cast(value, field_key.type)
