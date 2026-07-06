"""
Helpers for request body validation using Pydantic schemas.

Use validate_request_body(SchemaClass) in a resource to ensure the JSON body
matches the schema. On success returns the validated model instance; on
validation error raises WrongParameterException with a 400-style payload
(message + optional data with field-level errors).
"""

from flask import request

from pydantic import BaseModel, ConfigDict, ValidationError

from zou.app.services.exception import WrongParameterException
from zou.app.utils import fields


class BaseSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _format_validation_errors(exc: ValidationError):
    """
    Turn Pydantic ValidationError into a list of {field, message} dicts.
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
    Validate request JSON body against a Pydantic schema.

    Args:
        SchemaClass: A Pydantic BaseModel subclass (e.g. AddToDepartmentSchema).
        data: Optional dict to validate instead of request.json (e.g. for tests).

    Returns:
        An instance of SchemaClass with validated/coerced attributes.

    Raises:
        WrongParameterException: If body is missing or validation fails.
            The exception's .dict can contain a "errors" list with field/message.
    """
    if data is not None:
        payload = data
    else:
        payload = request.get_json(silent=True)
        if payload is None:
            # Fall back to form / query parameters so clients that still
            # POST credentials or params as URL args keep working (matches
            # the legacy ArgsMixin.get_args behavior). When both are absent
            # we pass an empty dict so schemas with only optional fields
            # still validate and required fields raise field-level errors.
            payload = request.values.to_dict() if request.values else {}
    try:
        return SchemaClass.model_validate(payload)
    except ValidationError as e:
        errors = _format_validation_errors(e)
        raise WrongParameterException(
            "Validation error.",
            dict={"errors": errors},
        )


def validate_id_list(required=True):
    """
    Validate that the request body is a JSON array of UUID strings and
    return it. Bulk endpoints (create tasks for shots, batch delete...)
    take a bare array as body. With required=False an absent or empty
    body returns None: those endpoints treat it as "no explicit
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
