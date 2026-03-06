import datetime
import logging
import urllib.parse

from babel.dates import format_datetime
from calendar import monthrange
from dateutil import relativedelta

from sqlalchemy.exc import StatementError

from flask_jwt_extended import create_access_token, get_jti, current_user

from zou.app.models.department import Department
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.organisation import Organisation
from zou.app.models.person import Person
from zou.app.models.time_spent import TimeSpent

from zou.app import config, file_store, db
from zou.app.utils import fields, events, cache, emails, date_helpers
from zou.app.utils.email_i18n import get_email_translation
from zou.app.services import index_service, auth_service, templates_service
from zou.app.stores import auth_tokens_store
from zou.app.services.exception import (
    PersonNotFoundException,
    PersonInProtectedAccounts,
    WrongParameterException,
)

logger = logging.getLogger(__name__)


def clear_person_cache():
    cache.cache.delete_memoized(_get_person_raw_for_cache)
    cache.cache.delete_memoized(get_person)
    cache.cache.delete_memoized(get_person_by_email)
    cache.cache.delete_memoized(get_person_by_desktop_login)
    cache.cache.delete_memoized(get_person_by_email_desktop_login)
    cache.cache.delete_memoized(get_active_persons)
    cache.cache.delete_memoized(get_persons)


def clear_organisation_cache():
    cache.cache.delete_memoized(get_organisation)
    cache.cache.delete_memoized(get_organisation, True)


@cache.memoize_function(120)
def get_persons(minimal=False):
    """
    Return all person stored in database.
    """
    persons = []
    for person in Person.query.all():
        if minimal:
            persons.append(person.present_minimal(relations=True))
        else:
            persons.append(person.serialize_safe(relations=True))
    return persons


def get_all_raw_active_persons():
    """
    Return all person stored in database without serialization.
    """
    return Person.get_all_by(active=True)


@cache.memoize_function(120)
def get_active_persons():
    """
    Return all persons with flag active set to True.
    """
    persons = (
        Person.query.filter_by(active=True)
        .order_by(Person.first_name)
        .order_by(Person.last_name)
        .all()
    )
    return fields.serialize_models(persons)


@cache.memoize_function(60)
def _get_person_raw_for_cache(person_id):
    """
    Internal function to get person and prepare it for caching.
    Expunges the object from session so it can be safely cached.
    This function is cached - it returns a detached Person object.

    Note: We don't pre-load departments here to avoid stale department data.
    Departments will be loaded fresh after merging into the session.
    """
    if person_id is None:
        raise PersonNotFoundException()

    try:
        person = Person.get(person_id)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()

    # Don't load departments here - we'll load them fresh after merging
    # This ensures departments are always up-to-date even if cached

    # Expunge from session so it can be cached without session conflicts
    # This is cheap - just removes from identity map, no DB query
    db.session.expunge(person)
    return person


def get_person_raw_cached(person_id):
    """
    Return given person as an active record, cached and merged into current session.
    This avoids session conflicts by caching expunged objects and merging on retrieval.

    Uses load=False to avoid database query on merge - we trust the cached data.
    Departments are loaded fresh after merging to ensure they're up-to-date.
    """
    cached_person = _get_person_raw_for_cache(person_id)
    # Merge into current session with load=False to avoid DB query
    merged_person = db.session.merge(cached_person, load=False)
    return merged_person


def get_person_raw(person_id):
    """
    Return given person as an active record.
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
def get_person(person_id, unsafe=False, relations=True):
    """
    Return given person as a dictionary.
    """
    person = get_person_raw(person_id)
    if unsafe:
        return person.serialize(relations=relations)
    else:
        return person.serialize_safe(relations=relations)


def get_person_by_email_raw(email):
    """
    Return person that matches given email as an active record.
    """
    person = Person.get_by(email=email, is_bot=False)

    if person is None:
        raise PersonNotFoundException()
    return person


@cache.memoize_function(120)
def get_person_by_email(email, unsafe=False, relations=False):
    """
    Return person that matches given email as a dictionary.
    """
    person = get_person_by_email_raw(email)
    if unsafe:
        return person.serialize(relations=relations)
    else:
        return person.serialize_safe(relations=relations)


@cache.memoize_function(120)
def get_person_by_desktop_login(desktop_login):
    """
    Return person that matches given desktop login as a dictionary. It is useful
    to authenticate user from their desktop session login.
    """
    try:
        person = Person.get_by(desktop_login=desktop_login, is_bot=False)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()
    return person.serialize()


def get_current_user(unsafe=False, relations=False):
    """
    Return person from its auth token (the one that does the request) as a
    dictionary.
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
    Return FIDO device names for the current user.
    """
    return current_user.fido_devices()


def get_current_user_raw():
    """
    Return person from its auth token (the one that does the request) as an
    active record.
    """
    # current_user is already a Person object from the auth callback
    # which uses get_person_raw_cached(). However, when merging with load=False,
    # relationships might not be loaded. We need to ensure departments are loaded.
    # Accessing departments triggers lazy loading if not already loaded.
    # Convert to list to force evaluation and ensure departments are loaded
    _ = (
        list(current_user.departments)
        if hasattr(current_user, "departments")
        else []
    )
    return current_user


def get_person_by_ldap_uid(ldap_uid):
    """
    Return person that matches given ldap_uid as a dictionary.
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
    Return person that matches given email or desktop login as a dictionary.
    """
    try:
        return get_person_by_email(email_or_desktop_login, unsafe=True)
    except PersonNotFoundException:
        return get_person_by_desktop_login(email_or_desktop_login)


def get_persons_map():
    """
    Return a dict of which keys are person_id and values are person.
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
    active=True,
    serialize=True,
):
    """
    Create a new person entry in the database. No operation are performed on
    password, so encrypted password is expected.
    """
    if departments is None:
        departments = []
    if email is not None:
        email = email.strip()

    if expiration_date is not None:
        if isinstance(expiration_date, str):
            expiration_date = date_helpers.get_date_from_string(
                expiration_date
            )
        try:
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
    Update password field for use matching given email.
    """
    person = get_person_by_email_raw(email)
    person.update({"password": password})
    clear_person_cache()
    logger.info("Password updated", extra={"email": email})
    return person.serialize()


def update_person(person_id, data, bypass_protected_accounts=False):
    """
    Update person entry with data given in parameter.
    """
    person = Person.get(person_id)
    if (
        not bypass_protected_accounts
        and person.email in config.PROTECTED_ACCOUNTS
        and not person.is_bot
    ):
        message = None
        if data.get("active") is False:
            message = (
                "Can't set this person as inactive it's a protected account."
            )
        elif data.get("role") is not None:
            message = "Can't change the role of this person it's a protected account."

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

    if "expiration_date" in data:
        access_token = create_access_token_for_raw_person(person)
    index_service.remove_person_index(person_id)
    if person.active:
        index_service.index_person(person)
    events.emit("person:update", {"person_id": person_id})
    clear_person_cache()
    if "expiration_date" in data:
        return {
            "access_token": access_token,
            **person.serialize(),
        }
    else:
        return person.serialize()


def delete_person(person_id):
    """
    Delete person entry from database.
    """
    person = Person.get(person_id)
    person_dict = person.serialize()
    person.delete()
    index_service.remove_person_index(person_id)
    events.emit("person:delete", {"person_id": person_id})
    clear_person_cache()
    logger.info("Person deleted", extra={"person_id": str(person_id)})
    return person_dict


def get_desktop_login_logs(person_id):
    """
    Get all logs for user desktop logins.
    """
    logs = (
        DesktopLoginLog.query.filter(DesktopLoginLog.person_id == person_id)
        .order_by(DesktopLoginLog.date.desc())
        .all()
    )
    return fields.serialize_list(logs)


def create_desktop_login_logs(person_id, date):
    """
    Add a new log entry for desktop logins.
    """
    log = DesktopLoginLog.create(person_id=person_id, date=date).serialize()
    update_person_last_presence(person_id)
    return log


def update_person_last_presence(person_id):
    """
    Update person presence field with the most recent time spent or
    desktop login log for this person.
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
    date = None
    if (
        log is not None
        and time_spent is not None
        and log.date > time_spent.date
    ):
        date = log.date
    elif time_spent is not None:
        date = time_spent.date
    return update_person(
        person_id, {"last_presence": date}, bypass_protected_accounts=True
    )


def get_presence_logs(year, month):
    """
    Return arrays of presence for a given month, adapted for a CSV rendering.
    Rows are users and columns represent the days of given month.
    """
    persons = get_active_persons()
    headers = [str(year)]
    csv_content = []

    _, limit = monthrange(year, month)
    headers += [str(i) for i in range(1, limit + 1)]
    start_date = datetime.datetime(year, month, 1, 0, 0, 0)
    end_date = datetime.date.today() + relativedelta.relativedelta(months=1)

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
    return person["role"] == "admin"


def invite_person(person_id):
    """
    Send an invitation email to given person (a mail telling him/her how to
    connect on Kitsu).
    """
    person = get_person(person_id)
    organisation = get_organisation()
    token = auth_service.generate_reset_token()
    auth_tokens_store.add(
        "reset-token-%s" % person["email"], token, ttl=3600 * 24 * 7
    )
    params = {"email": person["email"], "token": token, "type": "new"}
    query = urllib.parse.urlencode(params)
    reset_url = "%s://%s/reset-change-password?%s" % (
        config.DOMAIN_PROTOCOL,
        config.DOMAIN_NAME,
        query,
    )

    locale = person.get("locale") or getattr(config, "DEFAULT_LOCALE", "en_US")
    if hasattr(locale, "language"):
        locale = str(locale)
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


def send_password_changed_by_admin_email(person, admin_user, person_IP=None):
    """
    Send an email to the person notifying that an admin changed their password.
    """
    organisation = get_organisation()
    locale = person.get("locale") or getattr(config, "DEFAULT_LOCALE", "en_US")
    if hasattr(locale, "language"):
        locale = str(locale)
    time_string = format_datetime(
        date_helpers.get_utc_now_datetime(),
        tzinfo=person.get("timezone"),
        locale=person.get("locale"),
    )
    person_IP = person_IP or ""
    subject = get_email_translation(
        locale,
        "auth_password_changed_by_admin_subject",
        organisation_name=organisation["name"],
    )
    title = get_email_translation(
        locale, "auth_password_changed_by_admin_title"
    )
    html = get_email_translation(
        locale,
        "auth_password_changed_by_admin_body",
        first_name=person["first_name"],
        time_string=time_string,
        person_IP=person_IP,
    )
    email_html_body = templates_service.generate_html_body(
        title, html, locale=locale
    )
    emails.send_email(subject, email_html_body, person["email"], locale=locale)


def send_2fa_disabled_by_admin_email(person, admin_user, person_IP=None):
    """
    Send an email to the person notifying that an admin disabled their 2FA.
    """
    organisation = get_organisation()
    locale = person.get("locale") or getattr(config, "DEFAULT_LOCALE", "en_US")
    if hasattr(locale, "language"):
        locale = str(locale)
    time_string = format_datetime(
        date_helpers.get_utc_now_datetime(),
        tzinfo=person.get("timezone"),
        locale=person.get("locale"),
    )
    person_IP = person_IP or ""
    subject = get_email_translation(
        locale,
        "auth_2fa_disabled_by_admin_subject",
        organisation_name=organisation["name"],
    )
    title = get_email_translation(locale, "auth_2fa_disabled_by_admin_title")
    html = get_email_translation(
        locale,
        "auth_2fa_disabled_by_admin_body",
        first_name=person["first_name"],
        time_string=time_string,
        person_IP=person_IP,
    )
    email_html_body = templates_service.generate_html_body(
        title, html, locale=locale
    )
    emails.send_email(subject, email_html_body, person["email"], locale=locale)


@cache.memoize_function(120)
def get_organisation(sensitive=False):
    """
    Return organisation set up on this instance. It creates it if none exists.
    """
    organisation = Organisation.query.first()
    if organisation is None:
        organisation = Organisation.create(name="Kitsu")
    return organisation.present(sensitive=sensitive)


def update_organisation(organisation_id, data):
    """
    Update organisation entry with data given in parameter.
    """
    organisation = Organisation.get(organisation_id)
    organisation.update(data)
    events.emit("organisation:update", {"organisation_id": organisation_id})
    clear_organisation_cache()
    return organisation.present()


def is_user_limit_reached():
    """
    Returns true if the number of active users is equal and superior to the
    user limit set in the configuration.
    """
    nb_active_users = Person.query.filter(
        Person.active, Person.is_bot.isnot(True)
    ).count()
    return nb_active_users >= config.USER_LIMIT


def add_to_department(department_id, person_id):
    """
    Add to department.
    """
    person = get_person_raw(person_id)
    department = Department.get(department_id)
    person.departments.append(department)
    person.save()
    clear_person_cache()
    return person.serialize(relations=True)


def remove_from_department(department_id, person_id):
    """
    Remove from department.
    """
    person = get_person_raw(person_id)
    person.departments = [
        department
        for department in person.departments
        if str(department.id) != department_id
    ]
    person.save()
    clear_person_cache()
    return person.serialize(relations=True)


def clear_avatar(person_id):
    """
    Set person `has_avatar` field to False and delete related file.
    """
    person = get_person_raw(person_id)
    person.update({"has_avatar": False})
    clear_person_cache()
    if config.REMOVE_FILES:
        try:
            file_store.remove_picture("thumbnails", person_id)
        except Exception:
            pass
    return person.serialize()


def is_jti_revoked(jti):
    """
    Return True if the given token id is revoked.
    """
    return Person.query.filter_by(jti=jti).first() is None


def create_access_token_for_raw_person(person):
    """
    Create an access token for the given raw person.
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
