import re

from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.utils import cache, fields
from zou.app.services.exception import WrongParameterException
from sqlalchemy import distinct, func, or_

# Event names are made of lowercase words, digits and dashes on both sides of
# the colon separator. Anything else is rejected before it can reach a LIKE
# pattern: "%" and "_" would otherwise be interpreted as wildcards.
ALLOWED_NAME_PART = re.compile(r"^[a-z0-9-]+$")


def check_name_parts(values, parameter_name):
    """
    Raise a WrongParameterException if one of the given event name parts is
    not a plain lowercase word usable in a LIKE pattern.
    """
    for value in values:
        if not ALLOWED_NAME_PART.match(value or ""):
            raise WrongParameterException(
                f"The {parameter_name} parameter contains an invalid value"
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
    Return paginated events using cursor-based pagination.
    If cursor_event_id is set, it returns events older than this event.

    project_ids is a scoping allowlist, distinct from the project_id the
    caller asked for: it restricts the result to the projects the caller is
    allowed to see. Events without a project are never returned when it is
    set, since an IN clause does not match NULL.
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
        query = query.filter(ApiEvent.user_id.in_(person_ids))

    if name is not None:
        query = query.filter(ApiEvent.name == name)

    # Event names are "<object>:<action>", so an object filter is a prefix
    # match and an action filter is a suffix match.
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
        cursor_event = ApiEvent.query.get(cursor_event_id)
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
    Return the sorted list of the event names present in the log. It is used
    to build the object and action filters, so it must stay caller
    independent: no scoping is applied here.
    """
    names = ApiEvent.query.with_entities(distinct(ApiEvent.name)).all()
    return sorted(name for (name,) in names)


def create_login_log(person_id, ip_address, origin):
    """
    Create a new entry to register that someone logged in.
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
    Return paginated login logs using cursor-based pagination.
    If cursor_login_log_id is set, it returns login logs older than this log.
    """
    query = LoginLog.query.order_by(LoginLog.created_at.desc())

    if person_ids:
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
        cursor_log = LoginLog.query.get(cursor_login_log_id)
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
