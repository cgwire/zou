import datetime

from flask_jwt_extended import get_jti, create_access_token
from sqlalchemy.exc import StatementError

from zou.app.models.api_token import ApiToken
from zou.app.models.department import Department

from zou.app.utils import cache, fields, events

from zou.app.services import identities_service

from zou.app.services.exception import (
    DepartmentNotFoundException,
    ApiTokenNotFoundException,
)


def clear_api_token_cache():
    cache.cache.delete_memoized(get_api_token)
    cache.cache.delete_memoized(get_active_api_tokens)
    cache.cache.delete_memoized(get_api_tokens)
    identities_service.clear_identities_cache()


@cache.memoize_function(120)
def get_api_tokens(minimal=False):
    """
    Return all API tokens stored in database.
    """
    api_tokens = []
    for api_token in ApiToken.query.all():
        if not minimal:
            api_token.append(api_token.serialize_safe(relations=True))
        else:
            api_token.append(api_token.present_minimal(relations=True))
    return api_tokens


@cache.memoize_function(120)
def get_api_token(api_token_id, unsafe=False, relations=True):
    """
    Return given API token as a dictionary.
    """
    api_token = get_api_token_raw(api_token_id)
    if unsafe:
        return api_token.serialize(relations=relations)
    else:
        return api_token.serialize_safe(relations=relations)


@cache.memoize_function(120)
def get_active_api_tokens():
    """
    Return all API tokens with flag active set to True.
    """
    api_tokens = (
        ApiToken.query.filter_by(active=True).order_by(ApiToken.name).all()
    )
    return fields.serialize_models(api_tokens)


def get_api_token_raw(api_token_id):
    """
    Return given API token as an active record.
    """
    if api_token_id is None:
        raise ApiTokenNotFoundException()

    try:
        api_token = ApiToken.get(api_token_id)
    except StatementError:
        raise ApiTokenNotFoundException()

    if api_token is None:
        raise ApiTokenNotFoundException()
    return api_token


def create_api_token(
    email,
    name,
    description=None,
    days_duration=None,
    role="user",
    departments=[],
    serialize=True,
):
    """
    Create a new API token entry in the database.
    The token is not created at this moment, it needs to be created after."""
    if email is not None:
        email = email.strip()
    if not departments:
        departments = []

    try:
        departments_objects = [
            Department.get(department_id)
            for department_id in departments
            if department_id is not None
        ]
    except StatementError:
        raise DepartmentNotFoundException()

    api_token = ApiToken.create(
        name=name,
        email=email,
        description=description,
        days_duration=days_duration,
        role=role,
        departments=departments_objects,
    )
    events.emit("api-token:new", {"api_token_id": api_token.id})
    clear_api_token_cache()
    return api_token.serialize(relations=True) if serialize else api_token


def is_revoked(jti):
    """
    Return True if the given token id is revoked.
    """
    return ApiToken.query.filter_by(jti=jti).first() is None


def create_access_token_from_instance(instance):
    """
    Create an access token for the given instance.
    """
    expires_delta = None
    if instance.days_duration is not None:
        expires_delta = datetime.timedelta(days=instance.days_duration)
    access_token = create_access_token(
        identity=instance.id,
        additional_claims={
            "email": instance.email,
            "identity_type": "api_token",
        },
        expires_delta=expires_delta,
    )
    instance.jti = get_jti(access_token)
    instance.save()
    clear_api_token_cache()
    instance_dict = instance.serialize_safe()
    instance_dict["access_token"] = access_token
    return instance_dict
