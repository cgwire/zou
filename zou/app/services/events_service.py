import re

from sqlalchemy import distinct, func, or_

from zou.app.exceptions import WrongParameterException
from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.utils import cache, events, fields

# Event names contain lowercase words, digits and dashes on the two sides of
# the colon separator. Refuse all other characters before they go into a LIKE
# pattern. If not, "%" and "_" are wildcards. The match uses fullmatch, so no
# anchor is necessary and a trailing newline is refused.
ALLOWED_NAME_PART = re.compile(r"[a-z0-9-]+")


def check_name_parts(values, parameter_name):
    """
    If one of the given event name parts is not a plain lowercase word that a
    LIKE pattern can use, raise WrongParameterException.
    """
    for value in values:
        if not ALLOWED_NAME_PART.fullmatch(value or ""):
            raise WrongParameterException(
                f"The {parameter_name} parameter contains an invalid value"
            )
    return True


def check_person_ids(person_ids):
    """
    If one entry of a person_ids filter is not a valid id, raise
    WrongParameterException.
    """
    for person_id in person_ids or []:
        if not fields.is_valid_id(person_id):
            raise WrongParameterException(
                "The person_ids parameter contains an invalid id"
            )
    return True


def get_last_events(
    after=None,
    before=None,
    cursor_event_id=None,
    limit=100,
    only_files=False,
    project_id=None,
    project_ids=None,
    name=None,
    name_prefixes=None,
    name_suffixes=None,
    person_ids=None,
):
    """
    Return the events, paginated with a cursor. If cursor_event_id is set,
    return the events older than this event.

    project_ids is a scoping allowlist. It is not the project_id that the
    caller asked for. It limits the result to the projects that the caller can
    see. If it is set, the events without a project never come back, because an
    IN clause does not match NULL.

    If a filter value is not valid, or if the cursor event does not exist,
    raise WrongParameterException.
    """
    query = ApiEvent.query.order_by(ApiEvent.created_at.desc())

    if after is not None:
        query = query.filter(
            ApiEvent.created_at > func.cast(after, ApiEvent.created_at.type)
        )

    if before is not None:
        query = query.filter(
            ApiEvent.created_at < func.cast(before, ApiEvent.created_at.type)
        )

    if only_files:
        query = query.filter(
            ApiEvent.name.in_(
                (
                    "preview-file:add-file",
                    "organisation:set-thumbnail",
                    "person:set-thumbnail",
                    "project:set-thumbnail",
                )
            )
        )

    if project_id is not None:
        query = query.filter(ApiEvent.project_id == project_id)

    if project_ids is not None:
        query = query.filter(ApiEvent.project_id.in_(project_ids))

    if person_ids:
        check_person_ids(person_ids)
        query = query.filter(ApiEvent.user_id.in_(person_ids))

    if name is not None:
        query = query.filter(ApiEvent.name == name)

    # Event names are "<object>:<action>". Thus an object filter is a prefix
    # match, and an action filter is a suffix match.
    if name_prefixes:
        check_name_parts(name_prefixes, "name_prefixes")
        query = query.filter(
            or_(
                *[
                    ApiEvent.name.like(f"{prefix}:%")
                    for prefix in name_prefixes
                ]
            )
        )

    if name_suffixes:
        check_name_parts(name_suffixes, "name_suffixes")
        query = query.filter(
            or_(
                *[
                    ApiEvent.name.like(f"%:{suffix}")
                    for suffix in name_suffixes
                ]
            )
        )

    if cursor_event_id is not None:
        cursor_event = ApiEvent.get(cursor_event_id)
        if cursor_event is None:
            raise WrongParameterException(
                f"No event found with id: {cursor_event_id}"
            )
        query = query.filter(ApiEvent.created_at < cursor_event.created_at)

    events = query.limit(limit).all()
    return [
        fields.serialize_dict(
            {
                "id": event.id,
                "created_at": event.created_at,
                "name": event.name,
                "user_id": event.user_id,
                "project_id": event.project_id,
                "data": event.data,
            }
        )
        for event in events
    ]


@cache.memoize_function(3600)
def get_event_names():
    """
    Return the sorted list of the event names in the log. The object and action
    filters use this list, so it must not change with the caller. Thus this
    function applies no scoping.

    The index on api_event.name serves the DISTINCT, but the query still reads
    the full index. Thus the result is memoized. It becomes invalid only when a
    new name is stored.
    """
    names = ApiEvent.query.with_entities(distinct(ApiEvent.name)).all()
    return sorted(name for (name,) in names)


def invalidate_event_names_cache(name):
    """
    When a new event name is stored, remove the memoized list of names. The log
    filters use the list, so a new event type must show immediately, not after
    the TTL. The function reads the cached list first. Thus the usual case
    needs only one cache hit.
    """
    if name not in get_event_names():
        cache.cache.delete_memoized(get_event_names)
        return True
    return False


# Register the hook here, and do not import it from the write path. The events
# util is below the services, and must not use them.
events.add_save_hook(invalidate_event_names_cache)


def create_login_log(person_id, ip_address, origin):
    """
    Create a new entry to record that a person logged in.
    """
    login_log = LoginLog.create(
        person_id=person_id, ip_address=ip_address, origin=origin
    )
    return login_log.serialize()


def get_last_login_logs(
    after=None,
    before=None,
    cursor_login_log_id=None,
    limit=100,
    person_ids=None,
):
    """
    Return the login logs, paginated with a cursor. If cursor_login_log_id is
    set, return the login logs older than this log. If a person id is not
    valid, or if the cursor log does not exist, raise WrongParameterException.
    """
    query = LoginLog.query.order_by(LoginLog.created_at.desc())

    if person_ids:
        check_person_ids(person_ids)
        query = query.filter(LoginLog.person_id.in_(person_ids))

    if after is not None:
        query = query.filter(
            LoginLog.created_at > func.cast(after, LoginLog.created_at.type)
        )

    if before is not None:
        query = query.filter(
            LoginLog.created_at < func.cast(before, LoginLog.created_at.type)
        )

    if cursor_login_log_id is not None:
        cursor_log = LoginLog.get(cursor_login_log_id)
        if cursor_log is None:
            raise WrongParameterException(
                f"No login log found with id: {cursor_login_log_id}"
            )
        query = query.filter(LoginLog.created_at < cursor_log.created_at)

    login_logs = query.limit(limit).all()
    return [
        fields.serialize_dict(
            {
                "id": log.id,
                "created_at": log.created_at,
                "ip_address": log.ip_address,
                "person_id": log.person_id,
                "origin": log.origin,
            }
        )
        for log in login_logs
    ]
