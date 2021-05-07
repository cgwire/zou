import slugify
import datetime

from calendar import monthrange
from dateutil import relativedelta

from sqlalchemy.exc import StatementError

from flask_jwt_extended import get_jwt_identity

from zou.app.models.department import Department
from zou.app.models.desktop_login_log import DesktopLoginLog
from zou.app.models.organisation import Organisation
from zou.app.models.person import Person

from zou.app.utils import fields, events, cache, emails
from zou.app import config

from zou.app.services.exception import (
    DepartmentNotFoundException,
    PersonNotFoundException,
)


def clear_person_cache():
    cache.cache.delete_memoized(get_person)
    cache.cache.delete_memoized(get_person_by_email)
    cache.cache.delete_memoized(get_person_by_email_username)
    cache.cache.delete_memoized(get_person_by_desktop_login)
    cache.cache.delete_memoized(get_active_persons)
    cache.cache.delete_memoized(get_persons)


@cache.memoize_function(120)
def get_persons(minimal=False):
    """
    Return all person stored in database.
    """
    persons = []
    for person in Person.query.all():
        if not minimal:
            persons.append(person.serialize_safe())
        else:
            persons.append(person.present_minimal())
    return persons


@cache.memoize_function(120)
def get_active_persons():
    """
    Return all person with flag active set to True.
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
def get_person(person_id):
    """
    Return given person as a dictionary.
    """
    person = get_person_raw(person_id)
    return person.serialize_safe(relations=True)


@cache.memoize_function(120)
def get_person_by_email_username(email):
    """
    Return person that matches given email as a dictionary.
    """
    username = email.split("@")[0]

    for person in get_persons():
        first_name = slugify.slugify(person["first_name"])
        last_name = slugify.slugify(person["last_name"])
        person_username = "%s.%s" % (first_name, last_name)
        if person_username == username:
            return person

    raise PersonNotFoundException


def get_person_by_email_raw(email):
    """
    Return person that matches given email as an active record.
    """
    person = Person.get_by(email=email)

    if person is None:
        raise PersonNotFoundException()
    return person


@cache.memoize_function(120)
def get_person_by_email(email, unsafe=False):
    """
    Return person that matches given email as a dictionary.
    """
    person = get_person_by_email_raw(email)
    if unsafe:
        return person.serialize()
    else:
        return person.serialize_safe()


@cache.memoize_function(120)
def get_person_by_desktop_login(desktop_login):
    """
    Return person that matches given desktop login as a dictionary. It is useful
    to authenticate user from their desktop session login.
    """
    try:
        person = Person.get_by(desktop_login=desktop_login)
    except StatementError:
        raise PersonNotFoundException()

    if person is None:
        raise PersonNotFoundException()
    return person.serialize()


def get_current_user():
    """
    Return person from its auth token (the one that does the request) as a
    dictionary.
    """
    return get_person_by_email(get_jwt_identity())


def get_current_user_raw():
    """
    Return person from its auth token (the one that does the request) as an
    active record.
    """
    return get_person_by_email_raw(get_jwt_identity())


def create_person(
    email,
    password,
    first_name,
    last_name,
    phone="",
    role="user",
    desktop_login="",
    departments=None,
):
    """
    Create a new person entry in the database. No operation are performed on
    password, so encrypted password is expected.
    """
    if email is not None:
        email = email.strip()
    if not departments:
        departments = []

    try:
        departments_objects = [
            Department.get(department_id) for department_id in departments
        ]
    except StatementError:
        raise DepartmentNotFoundException()

    person = Person.create(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=role,
        desktop_login=desktop_login,
        departments=departments_objects
    )
    events.emit("person:new", {"person_id": person.id})
    clear_person_cache()
    return person.serialize(relations=True)


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
    if "email" in data and data["email"] is not None:
        data["email"] = data["email"].strip()
    person.update(data)
    events.emit("person:update", {"person_id": person_id})
    clear_person_cache()
    return person.serialize()


def delete_person(person_id):
    """
    Delete person entry from database.
    """
    person = Person.get(person_id)
    person_dict = person.serialize()
    person.delete()
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
    return DesktopLoginLog.create(person_id=person_id, date=date).serialize()


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
    organisation = get_organisation()
    person = get_person_raw(person_id)
    subject = "You are invited by %s to join their Kitsu production tracker" % (
        organisation["name"]
    )
    body = """Hello %s,

Your are invited by %s to collaborate on their Kitsu production tracker.
You can connect here to start using it:

%s://%s

Your login is: %s
Your password is: default

You will be invited to modify your password on first connection.

Thank you and see you soon on Kitsu,

%s Team
""" % (
        person.first_name,
        organisation["name"],
        config.DOMAIN_PROTOCOL,
        config.DOMAIN_NAME,
        person.email,
        organisation["name"],
    )
    html = """<p>Hello %s,</p>
<p>
Your are invited by %s to collaborate on their Kitsu production tracker.
You can connect here to start using it:
</p>
<p>
%s://%s
</p>
<p>
Your login is: <strong>%s</strong>
Your password is: <em>default</em>
</p>
<p>
You will be invited to modify your password on first connection.
</p>
<p>
Thank you and see you soon on Kitsu,
</p>
<p>
%s Team
</p>
""" % (
        person.first_name,
        organisation["name"],
        config.DOMAIN_PROTOCOL,
        config.DOMAIN_NAME,
        person.email,
        organisation["name"],
    )

    emails.send_email(subject, body, person.email, html=html)


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
    return organisation.present()


def is_user_limit_reached():
    """
    Returns true if the number of active users is equal and superior to the
    user limit set in the configuration.
    """
    nb_active_users = Person.query.filter(Person.active).count()
    return nb_active_users >= config.USER_LIMIT


def add_to_department(department_id, person_id):
    """
    Add to department.
    """
    person = get_person_raw(person_id)
    department = Department.get(department_id)
    person.departments = person.departments + [department]
    person.save()
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
    return person.serialize(relations=True)
