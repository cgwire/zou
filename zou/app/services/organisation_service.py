from zou.app.exceptions import OrganisationNotFoundException
from zou.app.models.organisation import Organisation
from zou.app.services import base_service
from zou.app.utils import cache, events


@cache.memoize_function(120)
def get_organisation(sensitive=False):
    """
    Return the organisation of this instance. If no organisation exists,
    create it.
    """
    organisation = Organisation.query.first()
    if organisation is None:
        organisation = Organisation.create(name="Kitsu")
    if sensitive:
        return organisation.present()
    return organisation.present_minimal()


def clear_organisation_cache():
    """
    Remove the memoized organisation from the cache.
    """
    cache.cache.delete_memoized(get_organisation)
    cache.cache.delete_memoized(get_organisation, True)


def update_organisation(organisation_id, data):
    """
    Update the given organisation with the given data. Emit
    organisation:update and clear the organisation cache.
    """
    organisation = base_service.get_instance(
        Organisation, organisation_id, OrganisationNotFoundException
    )
    organisation.update(data)
    events.emit("organisation:update", {"organisation_id": organisation_id})
    clear_organisation_cache()
    return organisation.present_minimal()


def get_user_limit():
    """
    Return the current user limit. Read it from Redis first, because all the
    workers share Redis. If Redis has no value, use the config file value.
    """
    from zou.app.stores.config_store import get_user_limit

    return get_user_limit()


def get_default_timezone():
    """
    Return the default timezone. Read it from Redis first, because all the
    workers share Redis. If Redis has no value, use the config file value.
    """
    from zou.app.stores.config_store import get_default_timezone

    return get_default_timezone()


def get_default_locale():
    """
    Return the default locale. Read it from Redis first, because all the
    workers share Redis. If Redis has no value, use the config file value.
    """
    from zou.app.stores.config_store import get_default_locale

    return get_default_locale()
