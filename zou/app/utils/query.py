import math
import uuid

import orjson as json
import sqlalchemy.orm as orm
from sqlalchemy import func, or_, tuple_, types as sa_types
from sqlalchemy.inspection import inspect

from zou.app import config
from zou.app.exceptions import WrongParameterException
from zou.app.utils import fields, string

# Some criterions accept sentinel values that are not UUIDs (e.g. "all"
# or "main" for episode_id). Thus, they must bypass the UUID validation.
EPISODE_ID_SENTINELS = ["all", "main"]


def get_query_criterions_from_request(request):
    """
    Change the request parameters into a dict. The keys are the attributes
    to filter on, and the values are the values to filter with.
    """
    criterions = {}
    for key, value in request.args.items():
        if key not in ["page"]:
            criterions[key] = value
    return criterions


def check_criterion_id_format(
    criterions, id_fields=("id", "project_id", "episode_id")
):
    """
    Make sure that the ID criterions of a request contain a valid UUID
    before they go into a custom SQL query. Resources that build queries
    by hand (the "*-and-tasks" endpoints) do not get the cast of
    apply_criterions_to_db_query. Without this check, an invalid UUID goes
    to the database and raises a StatementError (HTTP 500), not a 400.
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
    Apply the criterions of the HTTP request to the SQLAlchemy query object.
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

            if key == "name":
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


def apply_cursor(query, cursor_id=None, limit=None):
    """
    Limit the query to the rows after the given row, newest first (by
    creation date). The client walks a full listing request by request: it
    sends the ID of the last row that it got, until a page comes back
    short. Rows written during the walk never shift the other rows, as
    they do with pages. The ID sets the order of rows created together.
    """
    limit = limit or config.NB_RECORDS_PER_PAGE
    if limit < 0:
        raise WrongParameterException("limit must be a positive integer.")
    model = query.column_descriptions[0]["entity"]
    if cursor_id:
        cursor = model.get(cursor_id)
        if cursor is None:
            raise WrongParameterException("cursor_id matches no row.")
        if cursor.created_at is None:
            # PostgreSQL sorts the rows without a date before the dated ones.
            query = query.filter(
                or_(model.created_at.isnot(None), model.id < cursor.id)
            )
        else:
            query = query.filter(
                tuple_(model.created_at, model.id)
                < tuple_(cursor.created_at, cursor.id)
            )
    query = query.order_by(None).order_by(
        model.created_at.desc(), model.id.desc()
    )
    return query.limit(limit)


def is_whole_list(page=0, limit=None, cursor_id=None):
    """
    Tell whether the paging options of a listing ask for no page and no
    cursor walk. In this case, the listing answers with all its rows.
    """
    return page < 1 and not limit and not cursor_id


def get_paginated_results(
    query, page=0, limit=None, relations=False, cursor_id=None, serialize=None
):
    """
    Apply pagination to the query object. A page answers with an envelope.
    Without a page, a limit or a cursor ID answers with a plain list, which
    the client walks by cursor (see apply_cursor). Without all of these,
    the answer is the full list. If the listing has its own way to present
    the rows, the rows go through serialize.
    """
    if serialize is None:

        def serialize(entries):
            return fields.serialize_models(entries, relations=relations)

    if is_whole_list(page, limit, cursor_id):
        return serialize(query.all())
    elif page < 1:
        return serialize(apply_cursor(query, cursor_id, limit).all())
    else:
        limit = limit or config.NB_RECORDS_PER_PAGE
        total = query.count()
        offset = (page - 1) * limit

        nb_pages = int(math.ceil(total / float(limit)))
        # The ID is the last sort key of every paged listing. Without it,
        # rows that the listing order cannot separate (same name, same
        # date) could move from one page to another: one row comes two
        # times and another row never comes.
        model = query.column_descriptions[0]["entity"]
        query = query.order_by(model.id)
        query = query.limit(limit)
        query = query.offset(offset)

        if total < offset:
            # After the last page, the envelope still describes the full
            # collection: total stays the real count, as nb_pages does.
            result = {
                "data": [],
                "total": total,
                "nb_pages": nb_pages,
                "limit": limit,
                "offset": offset,
                "page": page,
            }
        else:
            models = serialize(query.all())
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
    """
    Return the rows of the query created after cursor_created_at, oldest
    first, at most limit of them, in a {data, total, limit} dict. total
    counts the full query, without the cursor filter.
    """
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
    Apply an order by clause to a SQLAlchemy query from a string parameter.
    """
    if sort_by in model.__table__.columns.keys():
        sort_field = model.__table__.columns[sort_by]
        if sort_by in ["created_at", "updated_at"]:
            sort_field = sort_field.desc()
    else:
        sort_field = model.updated_at.desc()
    return query.order_by(sort_field)


def cast_value(value, field_key):
    """
    Return the value, ready for comparison with the given column: the bare
    value for a NullType expression, a bool for a boolean column, else a
    SQL cast to the column type. If a boolean or a UUID is not valid,
    raise WrongParameterException.
    """
    # A hybrid expression built from functions that SQLAlchemy does not
    # know has the NullType: Person.full_name is a concat_ws inside a trim.
    # CAST(... AS NULL) cannot compile, and the CompileError is not a
    # StatementError, so it escaped as a 500 instead of a filter. The cast
    # only had to compare the bare value, and the code now does that.
    if isinstance(field_key.type, sa_types.NullType):
        return value

    # Some column types (ChoiceType, LocaleType, TimezoneType, ...) do not
    # implement python_type and raise NotImplementedError. They go to the
    # generic cast below, and the request does not crash.
    try:
        python_type = field_key.type.python_type
    except NotImplementedError:
        python_type = None
    if python_type is bool:
        try:
            return string.strtobool(value)
        except ValueError:
            raise WrongParameterException(f"Invalid boolean value: {value}")
    elif python_type is uuid.UUID:
        if (
            value
            and not isinstance(value, uuid.UUID)
            and not fields.is_valid_id(value)
        ):
            raise WrongParameterException(f"Invalid UUID value: {value}")
        return func.cast(value, field_key.type)
    else:
        return func.cast(value, field_key.type)
