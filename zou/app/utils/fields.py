import datetime
import re
import uuid
from enum import Enum
from ipaddress import IPv4Address

import sqlalchemy.orm as orm
from babel import Locale
from pytz import tzinfo
from sqlalchemy_utils.types.choice import Choice

# Anchored at both ends: re.match only anchors the start. An unanchored
# pattern accepted a valid UUID followed by any text ("<uuid>\n",
# "<uuid>?x=1") and let it go to the database. There, uuid.UUID() raises a
# StatementError (HTTP 500), not the 400 that the is_valid_id guards expect.
_UUID_RE = re.compile(
    r"\A[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}"
    r"-[a-fA-F0-9]{12}\Z"
)


def serialize_value(value, milliseconds=False):
    """
    Normalize the given value for specific field types. The aim is to make
    the result JSON serializable.
    """
    if isinstance(value, datetime.datetime):
        if milliseconds:
            # isoformat() drops the fraction of a round second, and then the
            # cursor listings cannot parse the value back.
            return value.isoformat(timespec="microseconds")
        else:
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
    elif isinstance(value, list):
        return serialize_list(value)
    elif isinstance(value, Locale):
        return str(value)
    elif isinstance(value, tzinfo.DstTzInfo):
        return str(value)
    elif isinstance(value, Choice):
        return value.code
    elif isinstance(value, Enum):
        return value.value
    elif isinstance(value, IPv4Address):
        return str(value)
    elif value is None:
        return None
    elif hasattr(value, "serialize"):
        return value.serialize()
    else:
        return value


def serialize_list(list_value):
    """
    Serialize a list of objects of any type into data structures that are
    JSON serializable.
    """
    return (
        list_value
        if list_value is None
        else [serialize_value(value) for value in list_value]
    )


def serialize_dict(dict_value):
    """
    Serialize a dict of objects of any type into data structures that are
    JSON serializable.
    """
    result = {}
    for key in dict_value.keys():
        result[key] = serialize_value(dict_value[key])

    return result


def serialize_orm_arrays(array_value):
    """
    Serialize an ORM array into the list of the IDs of its items.
    """
    return [serialize_value(val.id) for val in array_value]


def serialize_models(models, relations=False, milliseconds=False):
    """
    Serialize a list of models (useful for JSON dumps).
    """
    return [
        model.serialize(relations=relations, milliseconds=milliseconds)
        for model in models
        if model is not None
    ]


def present_models(models):
    """
    Present a list of models (useful for JSON dumps).
    """
    return [model.present() for model in models if model is not None]


def gen_uuid():
    """
    Generate a random unique identifier, as a uuid.UUID.
    """
    return uuid.uuid4()


def get_date_object(date_string, date_format="%Y-%m-%d"):
    """
    Parse the given string with the given format and return a datetime.
    Format for a full date string: %Y-%m-%dT%H:%M:%S
    """
    return datetime.datetime.strptime(date_string, date_format)


def get_default_date_object(date_string):
    """
    Parse the given "%Y-%m-%dT%H:%M:%S" string and return a datetime. If
    the string is empty or does not match, return None.
    """
    date_obj = None
    if date_string is not None and len(date_string) > 0:
        try:
            date_obj = get_date_object(
                date_string, date_format="%Y-%m-%dT%H:%M:%S"
            )
        except ValueError:
            pass
    return date_obj


def is_valid_id(value):
    """
    Check if the given value is a valid UUID or its string representation.
    Return the match object (truthy) or None.
    """
    return _UUID_RE.match(str(value))


def serialize_datetime(value):
    """
    Serialize a DateTime column value (or None) without the type dispatch
    of serialize_value. Use it in hot loops over known column types.
    """
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat()


def pick_fields(entries, field_names):
    """
    Keep only the given field names in each serialized entry (id and type
    always stay). This function runs after the full serialization on
    purpose: it comes after all the field masks based on permissions. Thus,
    it can only remove data, never expose it. It ignores unknown names.
    """
    kept = set(field_names) | {"id", "type"}
    return [
        {key: value for key, value in entry.items() if key in kept}
        for entry in entries
    ]


def boolean(value):
    """
    Parse "true"/"false" (case insensitive, also "1"/"0"/"on") as a boolean.
    Use it as a query argument type. On any other value, raise ValueError.
    """
    if isinstance(value, bool):
        return value
    if not value:
        raise ValueError("boolean type must be non-null")
    value = value.lower()
    if value in ("true", "1", "on"):
        return True
    if value in ("false", "0"):
        return False
    raise ValueError(f"Invalid literal for boolean(): {value}")
