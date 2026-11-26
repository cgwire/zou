import datetime
import hmac
import logging
import random
import string
import urllib.parse
from calendar import monthrange

from dateutil import relativedelta
from flask_jwt_extended import create_access_token, current_user, get_jti
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import selectinload

from zou.app import config, db, file_store
from zou.app.exceptions import (
    IsUserLimitReachedException,
    PersonInProtectedAccounts,
    PersonNotFoundException,
    SSOIdentityMismatchException,
    WrongParameterException,
)
from zou.app.models.department import Department
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.person import Person
from zou.app.models.project import ProjectPersonLink
from zou.app.models.studio import Studio
from zou.app.models.task import Task
from zou.app.models.time_spent import TimeSpent
from zou.app.services import (
    index_service,
    organisation_service,
    templates_service,
)
from zou.app.stores import auth_tokens_store
from zou.app.utils import cache, date_helpers, emails, events, fields
from zou.app.utils.email_i18n import get_email_translation

logger = logging.getLogger(__name__)

RESET_TOKENS_PER_ADDRESS = 10

_SHORT_PERSON_COLUMNS = (
    Person.id,
    Person.first_name,
    Person.last_name,
    Person.has_avatar,
    Person.role,
)


def clear_person_cache():
    """
    Remove the memoized person lists and serializations from the cache.
    """
    cache.cache.delete_memoized(_get_person_raw_for_cache)
    cache.cache.delete_memoized(get_person)
    cache.cache.delete_memoized(get_person_by_email)
    cache.cache.delete_memoized(get_person_by_desktop_login)
    cache.cache.delete_memoized(get_person_by_email_desktop_login)
    cache.cache.delete_memoized(get_active_persons)
    cache.cache.delete_memoized(get_persons)
    cache.cache.delete_memoized(get_short_person)


@cache.memoize_function(120)
def get_persons(minimal=False, include_guests=False):
    """
    Return all the persons of the database as safe dicts. If minimal is
    set, return minimal dicts. Never include the preview accounts.

    By default, do not include the guests (created by the shared playlist
    flow). They are not part of the studio team. Else, they show in the
    user context payload, the people page and many person dropdowns. To
    include them, give ``include_guests=True``.
    """
    persons = []
    query = Person.query.options(selectinload(Person.departments))
    query = query.filter(Person.preview_project_id.is_(None))
    if not include_guests:
        query = query.filter(Person.is_guest.is_(False))
    for person in query.all():
        if minimal:
            persons.append(person.present_minimal(relations=True))
        else:
            persons.append(person.serialize_safe(relations=True))
    return persons


@cache.memoize_function(120)
def get_active_persons():
    """
    Return all the persons whose active flag is True. Do not include the
    guests and the preview accounts.
    """
    persons = (
        Person.query.filter(
            Person.active,
            Person.is_guest.isnot(True),
            Person.preview_project_id.is_(None),
        )
        .order_by(Person.first_name)
        .order_by(Person.last_name)
        .all()
    )
    return fields.serialize_models(persons)


@cache.memoize_function(60)
def _get_person_raw_for_cache(person_id):
    """
    Internal function that gets a person and prepares it for the cache.
    Expunge the object from the session, so that the cache can keep it
    safely. This function is cached: it returns a detached Person object.

    Load the departments eagerly here, so that the cached instance keeps
    them in its state. After the expunge and a later merge with
    load=False, the database does not refresh the attributes of the
    instance. Thus, access to a relationship that needs a lazy load causes
    DetachedInstanceError. Each department change (add_to_department /
    remove_from_department) calls ``clear_person_cache()``. Thus, the data
    is never older than the memoize TTL.
    """
    if person_id is None:
        raise PersonNotFoundException()

    try:
        person = (
            Person.query.options(selectinload(Person.departments))
            .filter(Person.id == person_id)
            .one_or_none()
        )
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()

    # Expunge from the session, so that the cache causes no session conflict.
    # This is fast: it only removes the object from the identity map, with no
    # database query.
    db.session.expunge(person)
    return person


def get_person_raw_cached(person_id):
    """
    Return the given person as an active record, from the cache and merged
    into the current session. The cache keeps expunged objects and merges
    them when it gives them. This prevents session conflicts.

    The merge uses load=False to prevent a database query: the cached data
    is correct. The departments come from the cached object, which loaded
    them eagerly before the cache kept it.
    """
    cached_person = _get_person_raw_for_cache(person_id)
    merged_person = db.session.merge(cached_person, load=False)
    return merged_person


def get_person_raw(person_id):
    """
    Return the given person as an active record.
    """
    if person_id is None:
        raise PersonNotFoundException()

    try:
        person = Person.get(person_id)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()
    return person


@cache.memoize_function(120)
def get_person(person_id, unsafe=False, relations=True, minimal=False):
    """
    Return the given person as a dict.
    """
    person = get_person_raw(person_id)
    if unsafe:
        return person.serialize(relations=relations)
    elif minimal:
        return person.present_minimal(relations=relations)
    else:
        return person.serialize_safe(relations=relations)


def get_persons_by_ids(person_ids, minimal=False):
    """
    Return the persons that have the given IDs, as a list of safe dicts or
    of minimal dicts. Use one query for the persons and one for the
    departments of the minimal dicts, not one query per person.
    """
    if not person_ids:
        return []
    query = Person.query.filter(Person.id.in_(person_ids))
    if minimal:
        query = query.options(selectinload(Person.departments))
        return [
            person.present_minimal(relations=True) for person in query.all()
        ]
    return [person.serialize_safe() for person in query.all()]


def build_short_person(person):
    """
    Return the minimal author data of a comment or news author, guests
    included. Accept a full person row or a row with only the short
    columns. Thus, the full name is built here.
    """
    if person.first_name and person.last_name:
        full_name = f"{person.first_name} {person.last_name}"
    else:
        full_name = f"{person.first_name}{person.last_name}"
    return {
        "id": str(person.id),
        "first_name": person.first_name,
        "last_name": person.last_name,
        "full_name": full_name,
        "has_avatar": person.has_avatar,
        "role": getattr(person.role, "code", person.role),
    }


@cache.memoize_function(240)
def get_short_person(person_id):
    """
    Return the minimal author dict of the person that has the given ID. Load
    only the necessary columns, not the full person row.
    """
    try:
        row = (
            Person.query.with_entities(*_SHORT_PERSON_COLUMNS)
            .filter_by(id=person_id)
            .first()
        )
    except StatementError:
        raise PersonNotFoundException()
    if row is None:
        raise PersonNotFoundException()
    return build_short_person(row)


def get_short_persons_map(person_ids):
    """
    Return a {id: minimal author dict} map for the given IDs, with one query.
    """
    if not person_ids:
        return {}
    rows = Person.query.with_entities(*_SHORT_PERSON_COLUMNS).filter(
        Person.id.in_(person_ids)
    )
    return {str(row.id): build_short_person(row) for row in rows}


def get_persons_raw():
    """
    Return all the persons as active records, bots and inactive accounts
    included.
    """
    return Person.query.all()


def count_active_users():
    """
    Return the number of active human accounts. The user limit applies to
    this number.
    """
    return Person.query.filter(
        Person.active,
        Person.is_bot.isnot(True),
        Person.is_guest.isnot(True),
        Person.preview_project_id.is_(None),
    ).count()


def get_studio_raw_by_name(name):
    """
    Return the studio that has the given name as an active record, or None.
    """
    return Studio.get_by(name=name)


def get_department_raw_by_name(name):
    """
    Return the department that has the given name as an active record, or
    None.
    """
    return Department.get_by(name=name)


def import_person(email, data, department_ids=None, update=False):
    """
    Create the person that has the given email, from the columns of an
    import file. If update is set and the person exists, update it. If
    departments are given, set them. Return the safe serialization of the
    person.
    - If the user limit is reached and the row adds an active user, raise
      IsUserLimitReachedException.
    - If the person update route refuses the change, raise
      WrongParameterException.
    """
    person = Person.get_by(email=email, is_bot=False)
    created = person is None
    if created:
        if data.get("active", True) and is_user_limit_reached():
            raise IsUserLimitReachedException()
        person = Person.create(email=email, password=None, **data)
    elif update:
        if (
            person.email in config.PROTECTED_ACCOUNTS
            and str(person.id) != get_current_user()["id"]
        ):
            if person.active and data.get("active") is False:
                raise WrongParameterException(
                    "This person can't be set as inactive."
                )
            if data.get("role", person.role.code) != person.role.code:
                raise WrongParameterException(
                    "The role of this person can't be changed."
                )
        if (
            not person.active
            and data.get("active", False)
            and is_user_limit_reached()
        ):
            raise IsUserLimitReachedException()
        person.update(data)
    if created or update:
        if department_ids is not None:
            person.set_departments(department_ids)
        clear_person_cache()
    index_service.index_person(person)
    return person.serialize_safe()


def get_person_by_email_raw(email):
    """
    Return the person that has the given email as an active record.
    """
    # The database refuses a NUL character in a query, and no stored
    # address has one.
    if email is not None and "\x00" in email:
        raise PersonNotFoundException()
    person = Person.get_by(email=email, is_bot=False)

    if person is None:
        raise PersonNotFoundException()
    return person


@cache.memoize_function(120)
def get_person_by_email(email, unsafe=False, relations=False):
    """
    Return the person that has the given email as a dict.
    """
    person = get_person_by_email_raw(email)
    if unsafe:
        return person.serialize(relations=relations)
    else:
        return person.serialize_safe(relations=relations)


def get_person_by_sso_identity(protocol, issuer, subject):
    """
    Return the person linked to the given identity as a dict. The protocol
    ("oidc", "saml") gives the pair of columns that store the identity.
    """
    person = Person.get_by(
        **{
            f"{protocol}_issuer": issuer,
            f"{protocol}_subject": subject,
            "is_bot": False,
        }
    )
    if person is None:
        raise PersonNotFoundException()
    return person.serialize_safe()


def link_sso_identity(person_id, protocol, issuer, subject):
    """
    Link the given identity to the given person. If the person is already
    linked to a different subject of the same issuer, keep that link. The
    email is not a proof of the identity of the user who signs in. A
    different issuer means that the provider changed. Thus, the link
    changes to the new issuer.
    """
    person = Person.get(person_id)
    if (
        getattr(person, f"{protocol}_issuer") == issuer
        and getattr(person, f"{protocol}_subject") != subject
    ):
        raise SSOIdentityMismatchException()
    return update_person(
        person_id,
        {f"{protocol}_issuer": issuer, f"{protocol}_subject": subject},
        bypass_protected_accounts=True,
    )


@cache.memoize_function(120)
def get_person_by_desktop_login(desktop_login):
    """
    Return the person that has the given desktop login as a dict. Use it to
    authenticate a user from their desktop session login.
    """
    # create_person gives an empty desktop login to all the persons who
    # have none, and the column is not unique. Thus, a match on an empty
    # value gave the first such account, usually the admin of the install.
    if not desktop_login:
        raise PersonNotFoundException()
    try:
        person = Person.get_by(desktop_login=desktop_login, is_bot=False)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()
    return person.serialize()


def get_current_user(unsafe=False, relations=False):
    """
    Return the person of the auth token (the person who sends the request)
    as a dict.
    """
    data = current_user.serialize_safe(relations=relations)
    if unsafe:
        data["totp_secret"] = current_user.totp_secret
        data["email_otp_secret"] = current_user.email_otp_secret
        data["otp_recovery_codes"] = current_user.otp_recovery_codes
        data["fido_credentials"] = current_user.fido_credentials
        data["fido_devices"] = current_user.fido_devices()
    return data


def get_current_user_fido_devices():
    """
    Return the FIDO device names of the current user.
    """
    return current_user.fido_devices()


def build_assignee_filter():
    """
    Return the query filter for the tasks assigned to the current user. It
    is here, at the bottom of the service layers. Thus, the entity services
    can limit a list without an import of user_service.
    """
    return Task.assignees.contains(get_current_user_raw())


def get_current_user_raw():
    """
    Return the person of the auth token (the person who sends the request)
    as an active record.
    """
    # current_user comes from get_person_raw_cached() in the auth callback,
    # merged with load=False. Read the departments to make sure that they
    # are loaded before the caller uses them.
    _ = (
        list(current_user.departments)
        if hasattr(current_user, "departments")
        else []
    )
    return current_user


def get_person_by_ldap_uid(ldap_uid):
    """
    Return the person that has the given ldap_uid as a dict.
    """
    if ldap_uid is None:
        raise PersonNotFoundException()
    try:
        person = Person.get_by(ldap_uid=ldap_uid, is_bot=False)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()
    return person.serialize()


@cache.memoize_function(120)
def get_person_by_email_desktop_login(email_or_desktop_login):
    """
    Return the person that has the given email or desktop login as a dict.
    """
    # The two columns are not unique and accept NULL. Never put a falsy
    # identifier in a query: it can match any account with a blank value.
    # Public routes give a raw query parameter here.
    if not email_or_desktop_login:
        raise PersonNotFoundException()
    try:
        return get_person_by_email(email_or_desktop_login, unsafe=True)
    except PersonNotFoundException:
        return get_person_by_desktop_login(email_or_desktop_login)


def get_persons_map():
    """
    Return a dict whose keys are person_id values and whose values are
    persons.
    """
    persons = Person.query.all()
    return {str(person.id): person.serialize_safe() for person in persons}


def create_person(
    email,
    password,
    first_name,
    last_name,
    phone="",
    role="user",
    desktop_login="",
    departments=None,
    is_generated_from_ldap=False,
    ldap_uid=None,
    is_bot=False,
    expiration_date=None,
    studio_id=None,
    country=None,
    active=True,
    serialize=True,
):
    """
    Create a person entry in the database. This function does not change
    the password. Thus, give an encrypted password. Index the person, emit
    person:new and clear the person cache.

    Return the serialized person, with an access token for a bot. If
    serialize is False, return the active record. If the expiration date is
    in the past or not valid, raise WrongParameterException.
    """
    if departments is None:
        departments = []
    if email is not None:
        email = email.strip()

    if expiration_date is not None:
        try:
            # Parse the date in the guard. Here the date is the string that a
            # caller typed. The clause below catches the ValueError that an
            # unreadable date raises.
            if isinstance(expiration_date, str):
                expiration_date = date_helpers.get_date_from_string(
                    expiration_date
                )
            if expiration_date.date() < datetime.date.today():
                raise WrongParameterException(
                    "Expiration date can't be in the past."
                )
        except WrongParameterException:
            raise
        except (ValueError, TypeError) as e:
            logger.warning("Invalid expiration_date for create_person: %s", e)
            raise WrongParameterException("Expiration date is not valid.")

    person = Person.create(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=role,
        desktop_login=desktop_login,
        departments=departments,
        is_generated_from_ldap=is_generated_from_ldap,
        ldap_uid=ldap_uid,
        is_bot=is_bot,
        expiration_date=expiration_date,
        studio_id=studio_id,
        country=country,
        active=active,
    )
    if is_bot:
        access_token = create_access_token_for_raw_person(person)
    index_service.index_person(person)
    events.emit("person:new", {"person_id": person.id})
    clear_person_cache()
    logger.info(
        "Person created",
        extra={"person_id": str(person.id), "email": email},
    )
    if serialize:
        if is_bot:
            return {
                "access_token": access_token,
                **person.serialize(relations=True),
            }
        else:
            return person.serialize(relations=True)
    else:
        return person


def update_password(email, password):
    """
    Update the password field of the user that has the given email. The
    pending reset links of that person stop working.
    """
    person = get_person_by_email_raw(email)
    # Do this first. Thus, if Redis is not available, the password does
    # not change.
    revoke_reset_tokens(person.email)
    person.update({"password": password})
    clear_person_cache()
    logger.info("Password updated", extra={"email": email})
    return person.serialize()


def update_person(person_id, data, bypass_protected_accounts=False):
    """
    Update the given person with the given data. Index the person again,
    emit person:update and clear the person cache. If the person is a bot
    and data has an expiration date, make a new access token. Return it
    with the person.

    If data deactivates a protected account, or changes its role, email or
    bot flag, raise PersonInProtectedAccounts. If bypass_protected_accounts
    is set, do not do this check. If the expiration date is in the past or
    not valid, raise WrongParameterException.
    """
    person = Person.get(person_id)
    if (
        not bypass_protected_accounts
        and person.email in config.PROTECTED_ACCOUNTS
        and not person.is_bot
    ):
        message = None
        if "active" in data and not data["active"]:
            message = (
                "Can't set this person as inactive it's a protected account."
            )
        elif data.get("role") is not None:
            message = "Can't change the role of this person it's a protected account."
        elif "email" in data and data["email"] != person.email:
            message = "Can't change the email of this person it's a protected account."
        elif "is_bot" in data and data["is_bot"] != person.is_bot:
            message = "Can't change the bot flag of this person it's a protected account."

        if message is not None:
            raise PersonInProtectedAccounts(message)

    if "email" in data and data["email"] is not None:
        data["email"] = data["email"].strip()

    if "expiration_date" in data and data["expiration_date"] is not None:
        try:
            if (
                datetime.datetime.strptime(
                    data["expiration_date"], "%Y-%m-%d"
                ).date()
                < datetime.date.today()
            ):
                raise WrongParameterException(
                    "Expiration date can't be in the past."
                )
        except WrongParameterException:
            raise
        except (ValueError, TypeError) as e:
            logger.warning(
                "Invalid expiration_date for update_person %s: %s",
                person_id,
                e,
            )
            raise WrongParameterException("Expiration date is not valid.")

    person.update(data)

    # Only for bots, as on the person update route. For a person, this
    # token has no password check and stays valid after all the sessions.
    regenerate_token = person.is_bot and "expiration_date" in data
    if regenerate_token:
        access_token = create_access_token_for_raw_person(person)
    index_service.remove_person_index(person_id)
    if person.active:
        index_service.index_person(person)
    events.emit("person:update", {"person_id": person_id})
    clear_person_cache()
    if regenerate_token:
        return {
            "access_token": access_token,
            **person.serialize(),
        }
    else:
        return person.serialize()


def get_desktop_login_logs(person_id):
    """
    Return all the desktop login logs of the given user.
    """
    logs = (
        DesktopLoginLog.query.filter(DesktopLoginLog.person_id == person_id)
        .order_by(DesktopLoginLog.date.desc())
        .all()
    )
    return fields.serialize_list(logs)


def create_desktop_login_logs(person_id, date):
    """
    Add a desktop login log entry and update the last presence of the
    person.
    """
    log = DesktopLoginLog.create(person_id=person_id, date=date).serialize()
    update_person_last_presence(person_id)
    return log


def update_person_last_presence(person_id):
    """
    Update the presence field of the person with the most recent time spent
    or desktop login log of this person. If the field changed, return True.

    This function runs for each new time spent and desktop login. Thus, it
    writes only this field, and only when the day changes. It does not do
    these operations:
    - change updated_at (Kitsu puts it in the avatar URL)
    - index the person again
    - clear the person cache for the full instance
    - emit person:update, which makes all the connected clients load the
      person again.
    Kitsu never reads the field. The memoized persons get the new value
    when they expire.
    """
    log = (
        DesktopLoginLog.query.filter(DesktopLoginLog.person_id == person_id)
        .order_by(DesktopLoginLog.date.desc())
        .first()
    )
    time_spent = (
        TimeSpent.query.filter(TimeSpent.person_id == person_id)
        .order_by(TimeSpent.date.desc())
        .first()
    )
    dates = []
    if log is not None:
        # A login has a precision of one second. A time spent and this field
        # are days. Thus, cut the login to the day before the comparison.
        dates.append(log.date.date())
    if time_spent is not None:
        dates.append(time_spent.date)
    date = max(dates, default=None)
    changed = Person.query.filter(
        Person.id == person_id,
        Person.last_presence.is_distinct_from(date),
    ).update(
        # Set updated_at to its own value. Else, it gets the onupdate default.
        {"last_presence": date, "updated_at": Person.updated_at},
        synchronize_session=False,
    )
    Person.commit()
    return changed > 0


def get_presence_logs(year, month):
    """
    Return the presence arrays of the given month, for a CSV rendering.
    The rows are the users and the columns are the days of the month.
    """
    persons = get_active_persons()
    headers = [str(year)]
    csv_content = []

    _, limit = monthrange(year, month)
    headers += [str(i) for i in range(1, limit + 1)]
    start_date = datetime.datetime(year, month, 1, 0, 0, 0)
    # The sheet has the days of one month, and each login goes in the
    # column of its day number. Thus, a login of a later month would go
    # in the column that has the same number.
    end_date = start_date + relativedelta.relativedelta(months=1)

    csv_content.append(headers)
    for person in persons:
        row = [person["full_name"]]
        row += ["" for i in range(1, limit + 1)]
        logs = (
            DesktopLoginLog.query.filter(
                DesktopLoginLog.person_id == person["id"]
            )
            .filter(DesktopLoginLog.date >= start_date)
            .filter(DesktopLoginLog.date < end_date)
            .order_by(DesktopLoginLog.date)
            .all()
        )

        for log in logs:
            day = log.date.day
            row[day] = "X"
        csv_content.append(row)
    return csv_content


def is_admin(person):
    """
    If the given person dict has the admin role, return True.
    """
    return person["role"] == "admin"


def build_password_reset_url(email, token, token_type=None):
    """
    Build the URL that a user opens to choose a new password. It is the
    same link as in the password recovery and invitation emails.
    """
    params = {"email": email, "token": token}
    if token_type is not None:
        params["type"] = token_type
    query = urllib.parse.urlencode(params)
    return (
        f"{config.DOMAIN_PROTOCOL}://{config.DOMAIN_NAME}"
        f"/reset-change-password?{query}"
    )


def check_password_change_allowed(person_id):
    """
    Make sure that the current user can set the password of the given
    person. The current user can always change their own account. They
    cannot set the password of a protected account, or of a different admin
    who already has a password. If the check passes, return the person.
    Else, raise PersonInProtectedAccounts.
    """
    current_user = get_current_user()
    person = get_person(person_id)
    if person["id"] != current_user["id"]:
        if person["email"] in config.PROTECTED_ACCOUNTS:
            raise PersonInProtectedAccounts(
                "This user is in protected accounts."
            )
        elif person["role"] == "admin":
            person_raw = get_person_raw(person_id)
            if person_raw.password is not None:
                raise PersonInProtectedAccounts(
                    "An admin can't change another admin's password."
                )
    return person


def create_reset_token(email, ttl):
    """
    Store a new password reset token for the given email, as the person
    record has it, and return it. The token is valid for ttl seconds. The
    tokens of earlier emails stay valid, up to RESET_TOKENS_PER_ADDRESS
    tokens per address. If there are too many, remove the tokens that
    expire first.
    """
    token = generate_reset_token()
    auth_tokens_store.add_to_token_set(
        f"reset-tokens-{email}", token, ttl, RESET_TOKENS_PER_ADDRESS
    )
    return token


def is_reset_token_valid(email, token):
    """
    Return True if the given token is a valid password reset token of the
    person with the given email. The tokens are stored for the address of
    the person. Thus, the case of the given email is not important.
    """
    try:
        person = get_person_by_email_raw(email)
    except PersonNotFoundException:
        return False
    tokens = auth_tokens_store.get_token_set(f"reset-tokens-{person.email}")
    return token in tokens or _is_former_reset_token(email, token)


def use_reset_token(email, token):
    """
    Remove the given password reset token of the person with the given
    email. If the token was valid, return True. If two requests use the
    same link, only one gets True.
    """
    try:
        person = get_person_by_email_raw(email)
    except PersonNotFoundException:
        return False
    if auth_tokens_store.remove_from_token_set(
        f"reset-tokens-{person.email}", token
    ):
        return True
    return (
        _is_former_reset_token(email, token)
        and auth_tokens_store.delete(f"reset-token-{email}") == 1
    )


def _is_former_reset_token(email, token):
    # Old versions stored one token per address, under the address of
    # the link that they sent.
    stored_token = auth_tokens_store.get(f"reset-token-{email}")
    return stored_token is not None and hmac.compare_digest(
        stored_token.encode(), token.encode()
    )


def revoke_reset_tokens(email):
    """
    Remove the password reset tokens of the given email, as the person
    record has it.
    """
    auth_tokens_store.delete(f"reset-tokens-{email}")
    auth_tokens_store.delete(f"reset-token-{email}")


def get_or_create_password_reset_link(person_id):
    """
    Return the password reset link of the given person. If the reset token
    that expires last (for example from an invitation or a previous call)
    has one hour or more left, use it again. Else, make and store a new
    token, valid for 2 hours. It is the same link as in the password
    recovery email.
    """
    person = get_person(person_id)
    tokens = auth_tokens_store.get_token_set(f"reset-tokens-{person['email']}")
    token = max(tokens, key=tokens.get, default=None)
    if token is None or tokens[token] < 3600:
        token = create_reset_token(person["email"], 3600 * 2)
    return build_password_reset_url(person["email"], token)


def get_email_locale(person):
    """
    Return the locale to use when you write to the given person. When the
    dict comes directly from the ORM, it has a Babel Locale object. Change
    this object into its string form.
    """
    locale = person.get("locale") or config.DEFAULT_LOCALE
    if hasattr(locale, "language"):
        locale = str(locale)
    return locale


def invite_person(person_id):
    """
    Send an invitation email to the given person. The email tells the person
    how to connect to Kitsu. It has a password reset link with a new token,
    valid for 7 days.
    """
    person = get_person(person_id)
    organisation = organisation_service.get_organisation()
    token = create_reset_token(person["email"], 3600 * 24 * 7)
    reset_url = build_password_reset_url(
        person["email"], token, token_type="new"
    )

    locale = get_email_locale(person)
    subject = get_email_translation(
        locale,
        "auth_invitation_subject",
        organisation_name=organisation["name"],
    )
    title = get_email_translation(locale, "auth_invitation_title")
    html = get_email_translation(
        locale,
        "auth_invitation_body",
        first_name=person["first_name"],
        organisation_name=organisation["name"],
        email=person["email"],
        reset_url=reset_url,
    )
    email_html_body = templates_service.generate_html_body(
        title, html, locale=locale
    )
    emails.send_email(subject, email_html_body, person["email"], locale=locale)


def is_user_limit_reached():
    """
    If the number of active users is equal to or more than the user limit of
    the configuration, return True. Do not count the guests.
    """
    nb_active_users = Person.query.filter(
        Person.active,
        Person.is_bot.isnot(True),
        Person.is_guest.isnot(True),
        Person.preview_project_id.is_(None),
    ).count()
    return nb_active_users >= organisation_service.get_user_limit()


def add_to_department(department_id, person_id):
    """
    Add the person to the department. Clear the person cache and emit
    person:update.
    """
    person = get_person_raw(person_id)
    department = Department.get(department_id)
    person.departments.append(department)
    person.save()
    clear_person_cache()
    events.emit("person:update", {"person_id": person_id})
    return person.serialize_safe(relations=True)


def remove_from_department(department_id, person_id):
    """
    Remove the person from the department. Clear the person cache and emit
    person:update.
    """
    person = get_person_raw(person_id)
    person.departments = [
        department
        for department in person.departments
        if str(department.id) != department_id
    ]
    person.save()
    clear_person_cache()
    events.emit("person:update", {"person_id": person_id})
    return person.serialize_safe(relations=True)


def clear_avatar(person_id):
    """
    Set the `has_avatar` field of the person to False and delete the related
    file.
    """
    person = get_person_raw(person_id)
    person.update({"has_avatar": False})
    clear_person_cache()
    # update_person sets an avatar and emits an event. Also emit an event
    # when you remove an avatar. Else, the other connected clients continue
    # to ask for a picture that does not exist.
    events.emit("person:update", {"person_id": str(person_id)})
    try:
        file_store.remove_picture("thumbnails", person_id)
    except Exception:
        logger.warning(
            f"The avatar file of person {person_id} could not be removed.",
            exc_info=1,
        )
    return person.serialize()


def is_jti_revoked(jti):
    """
    If the given token id is revoked, return True.
    """
    return Person.query.filter_by(jti=jti).first() is None


def create_access_token_for_raw_person(person):
    """
    Create an access token for the given raw person. Save its id on the
    person. This revokes the previous token.
    """
    expires_delta = False
    if person.expiration_date is not None:
        expires_delta = (
            datetime.datetime.combine(
                person.expiration_date,
                datetime.datetime.max.time(),
            )
            - date_helpers.get_utc_now_datetime()
        )
    access_token = create_access_token(
        identity=person.id,
        additional_claims={
            "identity_type": "bot" if person.is_bot else "person_api",
        },
        expires_delta=expires_delta,
    )
    person.jti = get_jti(access_token)
    person.save()
    return access_token


def build_team_exists_filter(project_id):
    """
    Return the query filter that keeps only the rows of the projects whose
    team includes the user. It uses EXISTS, so it never multiplies the
    result rows.
    """
    current_user = get_current_user()
    return (
        ProjectPersonLink.query.filter(
            ProjectPersonLink.project_id == project_id
        )
        .filter(ProjectPersonLink.person_id == current_user["id"])
        .exists()
    )


def get_timezone():
    """
    Return the timezone of the current user. If the user set no timezone,
    return the default timezone of the instance.
    """
    try:
        timezone = get_current_user()["timezone"]
    except Exception:
        timezone = organisation_service.get_default_timezone()
    return timezone or organisation_service.get_default_timezone()


def generate_reset_token():
    """
    Make and return a reset token.
    """
    return "".join(
        random.SystemRandom().choice(string.ascii_uppercase + string.digits)
        for _ in range(64)
    )
