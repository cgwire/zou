from flask_jwt_extended import current_user

from zou.app.utils import cache
from zou.app.services import persons_service, api_tokens_service

from zou.app.services.exception import (
    IdentityNotFoundException,
    PersonNotFoundException,
    ApiTokenNotFoundException,
)


def clear_identities_cache():
    cache.cache.delete_memoized(get_identity_with_type_raw)
    cache.cache.delete_memoized(get_identity)


def get_current_identity(unsafe=False, relations=False):
    """
    Return identity from its auth token (the one that does the request) as a
    dictionary.
    """
    if unsafe:
        return current_user.serialize(relations=relations)
    else:
        return current_user.serialize_safe(relations=relations)


def get_current_identity_raw():
    """
    Return identity from its auth token (the one that does the request) as an
    active record.
    """
    return current_user


@cache.memoize_function(120)
def get_identity_with_type_raw(id, identity_type=None):
    """
    Return given identity with identity_type.
    """
    if identity_type not in ["person", "api_token"]:
        raise IdentityNotFoundException()
    elif identity_type == "person":
        return persons_service.get_person_raw(id)
    elif identity_type == "api_token":
        return api_tokens_service.get_api_token_raw(id)


def get_identity_raw(id):
    """
    Return given identity.
    """
    try:
        return persons_service.get_person_raw(id)
    except PersonNotFoundException:
        try:
            return api_tokens_service.get_api_token_raw(id)
        except ApiTokenNotFoundException:
            raise IdentityNotFoundException()


@cache.memoize_function(120)
def get_identity(id):
    """
    Return given identity as a dictionary.
    """
    try:
        return persons_service.get_person(id)
    except PersonNotFoundException:
        try:
            return api_tokens_service.get_api_token(id)
        except ApiTokenNotFoundException:
            raise IdentityNotFoundException()
