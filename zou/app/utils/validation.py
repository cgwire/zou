"""
Helpers for request body validation with Pydantic schemas.

Use validate_request_body(SchemaClass) in a resource to make sure that the
JSON body matches the schema. If the validation succeeds, it returns the
validated model instance. If the validation fails, it raises
WrongParameterException with a 400-style payload (message + optional data
with field-level errors).
"""

from flask import request
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from zou.app.exceptions import WrongParameterException
from zou.app.utils import fields


class BaseSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _format_validation_errors(exc: ValidationError):
    """
    Change a Pydantic ValidationError into a list of {field, message}
    dicts.
    """
    return [
        {
            "field": ".".join(str(loc) for loc in err["loc"] if loc != "body"),
            "message": err.get("msg", "Invalid value"),
        }
        for err in exc.errors()
    ]


def validate_request_body(SchemaClass, *, data=None):
    """
    Validate the request JSON body against a Pydantic schema.

    Args:
        SchemaClass: A Pydantic BaseModel subclass
            (e.g. AddToDepartmentSchema).
        data: Optional dict to validate instead of request.json
            (e.g. for tests).

    Returns:
        An instance of SchemaClass with validated/coerced attributes.

    Raises:
        WrongParameterException: If the validation fails. If the JSON
            body is missing, the function validates the form or query
            parameters, or an empty dict if there are none.
            The .dict of the exception can contain an "errors" list with
            field/message.
    """
    if data is not None:
        payload = data
    else:
        payload = request.get_json(silent=True)
        if payload is None:
            # Use the form or query parameters, so that clients that still
            # POST credentials or params as URL args continue to work (same
            # behavior as the legacy ArgsMixin.get_args). If both are
            # absent, use an empty dict: schemas with only optional fields
            # still validate, and required fields raise field-level errors.
            payload = request.values.to_dict() if request.values else {}
    try:
        return SchemaClass.model_validate(payload)
    except ValidationError as e:
        errors = _format_validation_errors(e)
        raise WrongParameterException(
            "Validation error.",
            dict={"errors": errors},
        )


def validate_request_list(SchemaClass):
    """
    Validate a request body that is a JSON array of objects. Validate each
    object against the given Pydantic schema and return the list of
    instances.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        raise WrongParameterException("Request body must be a JSON array.")
    try:
        return TypeAdapter(list[SchemaClass]).validate_python(payload)
    except ValidationError as e:
        raise WrongParameterException(
            "Validation error.",
            dict={"errors": _format_validation_errors(e)},
        )


def validate_id_list(required=True):
    """
    Validate that the request body is a JSON array of UUID strings and
    return it. Bulk endpoints (create tasks for shots, batch delete...)
    take a bare array as body. If required=False and the body is absent
    or empty, return None: these endpoints read it as "no explicit
    selection" and target every entity of the scope.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        if not required and payload in (None, {}):
            return None
        raise WrongParameterException("Request body must be a JSON array.")
    for entity_id in payload:
        if not isinstance(entity_id, str) or not fields.is_valid_id(entity_id):
            raise WrongParameterException(
                "Request body must only contain valid UUIDs."
            )
    return payload
