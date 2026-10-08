from zou.app.models.organisation import Organisation
from zou.app.utils import events, cache
from zou.app.services import base_service
from zou.app.exceptions import OrganisationNotFoundException


@cache.memoize_function(120)
def get_organisation(sensitive=False):
    """
    Return organisation set up on this instance. It creates it if none exists.
    """
    organisation = Organisation.query.first()
    if organisation is None:
        organisation = Organisation.create(name="Kitsu")
    if sensitive:
        return organisation.present()
    return organisation.present_minimal()


def clear_organisation_cache():
    """
    Drop the memoized organisation.
    """
    cache.cache.delete_memoized(get_organisation)
    cache.cache.delete_memoized(get_organisation, True)


def update_organisation(organisation_id, data):
    """
    Update organisation entry with data given in parameter.
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
    Returns the current user limit, reading from Redis first (shared
    across workers) and falling back to the config file value.
    """
    from zou.app.stores.config_store import get_user_limit

    return get_user_limit()


def get_default_timezone():
    """
    Returns the default timezone, reading from Redis first (shared
    across workers) and falling back to the config file value.
    """
    from zou.app.stores.config_store import get_default_timezone

    return get_default_timezone()


def get_default_locale():
    """
    Returns the default locale, reading from Redis first (shared
    across workers) and falling back to the config file value.
    """
    from zou.app.stores.config_store import get_default_locale

    return get_default_locale()
