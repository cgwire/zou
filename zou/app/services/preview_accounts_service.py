import datetime
import secrets

from flask import current_app

from zou.app.exceptions import (
    PreviewAccountNotFoundException,
    PreviewAccountsUnavailableException,
)
from zou.app.models.person import Person
from zou.app.services import (
    cascade_deletion_service,
    persons_service,
    projects_service,
)
from zou.app.utils import auth, date_helpers

PREVIEW_OPEN_DURATION = datetime.timedelta(hours=1)


def is_available():
    """
    Return True if preview accounts are available. They use the local password
    login: other strategies cannot authenticate them.
    """
    return current_app.config["AUTH_STRATEGY"] == "auth_local_classic"


def get_preview_account_raw(project_id):
    """
    Return the preview account of the given project, or None.
    """
    return Person.get_by(preview_project_id=project_id)


def _serialize(person):
    return {
        "id": str(person.id),
        "email": person.email,
        "full_name": person.full_name,
        "preview_open_until": (
            person.preview_open_until.isoformat()
            if person.preview_open_until
            else None
        ),
    }


def get_preview_account(project_id):
    """
    Return the preview account of the given project as a dict, or None.
    """
    person = get_preview_account_raw(project_id)
    return None if person is None else _serialize(person)


def create_or_reset_preview_account(project_id):
    """
    Create the preview account of the given project, or replace its password.
    In the two cases, the access window closes, and this stops all sessions.
    The pending password reset links of the account also stop working. Return
    the account as a dict and its clear password.
    """
    if not is_available():
        raise PreviewAccountsUnavailableException(
            "Preview accounts require the local authentication strategy"
        )
    project = projects_service.get_project_raw(project_id)
    password = secrets.token_urlsafe(12)
    hashed = auth.encrypt_password(password)
    person = get_preview_account_raw(project_id)
    if person is None:
        # Do not use create_person: it indexes the account and emits person:new
        # before preview_project_id is set.
        person = Person.create(
            email=f"preview-{secrets.token_hex(6)}@preview.kitsu.invalid",
            password=hashed,
            first_name="Preview",
            last_name=project.name,
            role="client",
            preview_project_id=project.id,
        )
        projects_service.add_team_member(project.id, person.id)
    else:
        # Do this first, so that the reset changes nothing without Redis.
        persons_service.revoke_reset_tokens(person.email)
        person.update(
            {
                "password": hashed,
                "preview_opened_at": None,
                "preview_open_until": None,
            }
        )
    persons_service.clear_person_cache()
    return _serialize(person), password


def set_preview_account_open(project_id, is_open):
    """
    Open or close the access window. If the window of the account is already
    open, make it longer. Return the account as a dict.
    """
    person = get_preview_account_raw(project_id)
    if person is None:
        raise PreviewAccountNotFoundException(
            "No preview account for this project"
        )
    if is_open:
        now = date_helpers.get_utc_now_datetime()
        if (
            person.preview_open_until is None
            or person.preview_open_until < now
        ):
            person.preview_opened_at = now
        person.preview_open_until = now + PREVIEW_OPEN_DURATION
    else:
        person.preview_opened_at = None
        person.preview_open_until = None
    person.save()
    persons_service.clear_person_cache()
    return _serialize(person)


def delete_preview_account(project_id):
    """
    Remove the preview account of the given project, if it exists.
    """
    cascade_deletion_service.remove_preview_account(project_id)


def _to_epoch(value):
    return value.replace(tzinfo=datetime.timezone.utc).timestamp()


def is_preview_session_valid(person, issued_at):
    """
    Return True if a preview session is valid. A preview session is valid only
    while the window is open, and only if the token was issued after the window
    opened.
    """
    if person.preview_open_until is None:
        return False
    if person.preview_open_until < date_helpers.get_utc_now_datetime():
        return False
    if (
        issued_at is not None
        and person.preview_opened_at is not None
        and issued_at < int(_to_epoch(person.preview_opened_at))
    ):
        return False
    return True
