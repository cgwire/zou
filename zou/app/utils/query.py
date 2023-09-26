import math

from zou.app import app
from zou.app.utils import fields, string
from sqlalchemy import func


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


def apply_criterions_to_db_query(model, db_query, criterions):
    """
    Apply criterions given in HTTP request to the sqlachemy db query object.
    """
    if "name" in criterions and hasattr(model, "name"):
        value = criterions["name"]
        db_query = db_query.filter(model.name.ilike(value))
        del criterions["name"]

    return db_query.filter_by(**criterions)


def get_paginated_results(query, page, limit=None, relations=False):
    """
    Apply pagination to the query object.
    """
    if page < 1:
        entries = query.all()
        return fields.serialize_models(entries, relations=relations)
    else:
        limit = limit or app.config["NB_RECORDS_PER_PAGE"]
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
        return string.strtobool(value)
    else:
        return func.cast(value, field_key.type)
