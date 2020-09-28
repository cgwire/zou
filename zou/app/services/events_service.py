from zou.app.models.event import ApiEvent
from zou.app.models.login_log import LoginLog
from zou.app.utils import fields


def get_last_events(
    after=None,
    before=None,
    page_size=100,
    only_files=False,
    project_id=None
):
    """
    Return last 100 events published. If before parameter is set, it returns
    last 100 events before this date.
    """
    query = ApiEvent.query.order_by(ApiEvent.created_at.desc())

    if after is not None:
        query = query.filter(ApiEvent.created_at > after)

    if before is not None:
        query = query.filter(ApiEvent.created_at < before)

    if only_files:
        query = query.filter(ApiEvent.name.in_((
            "preview-file:add-file",
            "organisation:set-thumbnail",
            "person:set-thumbnail",
            "project:set-thumbnail",
        )))

    if project_id is not None:
        query = query.filter(ApiEvent.project_id == project_id)

    events = query.limit(page_size).all()
    return [
        fields.serialize_dict({
            "id": event.id,
            "created_at": event.created_at,
            "name": event.name,
            "user_id": event.user_id,
            "data": event.data,
        })
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


def get_last_login_logs(before=None, page_size=100):
    """
    Return last 100 login logs published. If before parameter is set, it returns
    last 100 login logs before this date.
    """
    query = LoginLog.query.order_by(LoginLog.created_at.desc()).with_entities(
        LoginLog.created_at, LoginLog.ip_address, LoginLog.person_id
    )

    if before is not None:
        query = query.filter(LoginLog.created_at < before)

    login_logs = query.limit(page_size).all()
    return [
        {
            "created_at": fields.serialize_value(created_at),
            "ip_address": fields.serialize_value(ip_address),
            "person_id": fields.serialize_value(person_id),
        }
        for (created_at, ip_address, person_id) in login_logs
    ]
