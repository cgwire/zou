import datetime
import re
import uuid
import sqlalchemy.orm as orm

from pytz import tzinfo
from babel import Locale
from ipaddress import IPv4Address
from sqlalchemy_utils.types.choice import Choice


def serialize_value(value):
    """
    Utility function to handle the normalizing of specific fields.
    The aim is to make the result JSON serializable
    """
    if isinstance(value, datetime.datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    elif isinstance(value, uuid.UUID):
        return str(value)
    elif isinstance(value, dict):
        return serialize_dict(value)
    elif isinstance(value, orm.collections.InstrumentedList):
        return serialize_orm_arrays(value)
    elif isinstance(value, bytes):
        return value.decode("utf-8")
    elif isinstance(value, str):
        return value
    elif isinstance(value, int):
        return value
    elif isinstance(value, list):
        return serialize_list(value)
    elif isinstance(value, Locale):
        return str(value)
    elif isinstance(value, tzinfo.DstTzInfo):
        return str(value)
    elif isinstance(value, Choice):
        return value.code
    elif isinstance(value, IPv4Address):
        return str(value)
    elif value is None:
        return None
    elif isinstance(value, object):
        if hasattr(value, "serialize"):
            return value.serialize()
        else:
            return value
    else:
        return value


def serialize_list(list_value):
    """
    Serialize a list of any kind of objects into data structures
    that are JSON serializable.
    """
    return [serialize_value(value) for value in list_value]


def serialize_dict(dict_value):
    """
    Serialize a dict of any kind of objects into data structures that are JSON
    serializable.
    """
    result = {}
    for key in dict_value.keys():
        result[key] = serialize_value(dict_value[key])

    return result


def serialize_orm_arrays(array_value):
    """
    Serialize a orm array into simple data structures (useful for json dumping).
    """
    return [serialize_value(val.id) for val in array_value]


def serialize_models(models, relations=False):
    """
    Serialize a list of models (useful for json dumping)
    """
    return [
        model.serialize(relations=relations)
        for model in models
        if model is not None
    ]


def gen_uuid():
    """
    Generate a unique identifier (useful for json dumping).
    """
    return uuid.uuid4()


def get_date_object(date_string, date_format="%Y-%m-%d"):
    """
    Shortcut for date parsing (useful for json dumping).
    Format for full date string: %Y-%m-%dT%H:%M:%S
    """
    return datetime.datetime.strptime(date_string, date_format)


def get_default_date_object(date_string):
    """
    Shortcut for date parsing at default format.
    """
    date_obj = None
    if date_string is not None and len(date_string) > 0:
        try:
            date_obj = get_date_object(
                date_string,
                date_format="%Y-%m-%dT%H:%M:%S"
            )
        except ValueError:
            pass
    return date_obj


def is_valid_id(uuid):
    _UUID_RE = re.compile(
        "([a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}){1}"
    )
    return _UUID_RE.match(uuid)
