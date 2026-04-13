from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.utils import fields
from zou.app.services.exception import WrongParameterException
from sqlalchemy import func


def get_last_events(
    after=None,
    before=None,
    cursor_event_id=None,
    limit=100,
    only_files=False,
    project_id=None,
    name=None,
):
    """
    Return paginated events using cursor-based pagination.
    If cursor_event_id is set, it returns events older than this event.
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

    if name is not None:
        query = query.filter(ApiEvent.name == name)

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
                "data": event.data,
            }
        )
        for event in events
    ]


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
):
    """
    Return paginated login logs using cursor-based pagination.
    If cursor_login_log_id is set, it returns login logs older than this log.
    """
    query = LoginLog.query.order_by(LoginLog.created_at.desc())

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
