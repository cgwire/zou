import datetime
import urllib.parse

from calendar import monthrange
from dateutil import relativedelta

from sqlalchemy.exc import StatementError

from babel.dates import format_datetime

from flask_jwt_extended import create_access_token, get_jti, current_user

from zou.app.models.department import Department
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.organisation import Organisation
from zou.app.models.person import Person
from zou.app.models.time_spent import TimeSpent

from zou.app import config, file_store
from zou.app.utils import fields, events, cache, emails, date_helpers
from zou.app.services import index_service, auth_service
from zou.app.stores import auth_tokens_store
from zou.app.services.exception import (
    PersonNotFoundException,
    PersonInProtectedAccounts,
    WrongParameterException,
)


def clear_person_cache():
    cache.cache.delete_memoized(get_person)
    cache.cache.delete_memoized(get_person_by_email)
    cache.cache.delete_memoized(get_person_by_desktop_login)
    cache.cache.delete_memoized(get_person_by_email_desktop_login)
    cache.cache.delete_memoized(get_active_persons)
    cache.cache.delete_memoized(get_persons)


def clear_oranisation_cache():
    cache.cache.delete_memoized(get_organisation)


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
    if unsafe:
        return current_user.serialize(relations=relations)
    else:
        return current_user.serialize_safe(relations=relations)


def get_current_user_raw():
    """
    Return person from its auth token (the one that does the request) as an
    active record.
    """
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
    departments=[],
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
    if email is not None:
        email = email.strip()

    if expiration_date is not None:
        try:
            if (
                date_helpers.get_date_from_string(expiration_date).date()
                < datetime.date.today()
            ):
                raise WrongParameterException(
                    "Expiration date can't be in the past."
                )
        except:
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
    return person.serialize()


def update_person(person_id, data):
    """
    Update person entry with data given in parameter.
    """
    person = Person.get(person_id)
    if person.email in config.PROTECTED_ACCOUNTS:
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
        except:
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
    desktop login log.
    """
    log = DesktopLoginLog.query.order_by(DesktopLoginLog.date.desc()).first()
    time_spent = TimeSpent.query.order_by(TimeSpent.date.desc()).first()
    date = None
    if (
        log is not None
        and time_spent is not None
        and log.date > time_spent.date
    ):
        date = log.date
    elif time_spent is not None:
        date = time_spent.date
    return update_person(person_id, {"last_presence": date})


def get_presence_logs(year, month):
    """
    Return arrays of presence for a given month, adapted for a CSV rendering.
    Rows are users and columns represent the days of given month.
    """
    persons = get_active_persons()
    headers = [str(year)]
    csv_content = []

    (_, limit) = monthrange(year, month)
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
        "reset-token-%s" % person["email"], token, ttl=3600 * 24 * 2
    )
    subject = (
        "You are invited by %s to join their Kitsu production tracker"
        % (organisation["name"])
    )
    params = {"email": person["email"], "token": token}
    query = urllib.parse.urlencode(params)
    reset_url = "%s://%s/reset-change-password?%s" % (
        config.DOMAIN_PROTOCOL,
        config.DOMAIN_NAME,
        query,
    )

    time_string = format_datetime(
        date_helpers.get_utc_now_datetime(),
        tzinfo=person["timezone"],
        locale=person["locale"],
    )

    html = f"""<p>Hello {person["first_name"]},</p>
<p>
You are invited by {organisation["name"]} to collaborate on their Kitsu production tracker.
</p>
<p>
Your login is: <strong>{person["email"]}</strong>
</p>
<p>
You are invited to set your password by following this link: <a href="{reset_url}">{reset_url}</a>
</p>
<p>
This link will expire after 2 days. After, you have to request to reset your password.
The invitation was sent at this date: {time_string}.
</p>
<p>
Thank you and see you soon on Kitsu,
</p>
<p>
{organisation["name"]} Team
</p>
"""

    emails.send_email(subject, html, person["email"])


@cache.memoize_function(120)
def get_organisation():
    """
    Return organisation set up on this instance. It creates it if none exists.
    """
    organisation = Organisation.query.first()
    if organisation is None:
        organisation = Organisation.create(name="Kitsu")
    return organisation.present()


def update_organisation(organisation_id, data):
    """
    Update organisation entry with data given in parameter.
    """
    organisation = Organisation.get(organisation_id)
    organisation.update(data)
    events.emit("organisation:update", {"organisation_id": organisation_id})
    clear_oranisation_cache()
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
        except BaseException:
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
