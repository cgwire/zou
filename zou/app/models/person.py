import sys

from sqlalchemy_utils import UUIDType, EmailType, LocaleType, TimezoneType
from sqlalchemy.dialects.postgresql import JSONB

from pytz import timezone as pytz_timezone
from babel import Locale

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app import config


department_link = db.Table(
    "department_link",
    db.Column("person_id", UUIDType(binary=False), db.ForeignKey("person.id")),
    db.Column(
        "department_id", UUIDType(binary=False), db.ForeignKey("department.id")
    ),
)


class Person(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a member of the studio (and an API user).
    """

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(EmailType, unique=True)
    phone = db.Column(db.String(30))

    active = db.Column(db.Boolean(), default=True)
    last_presence = db.Column(db.Date())

    password = db.Column(db.LargeBinary(60))
    desktop_login = db.Column(db.String(80))
    shotgun_id = db.Column(db.Integer, unique=True)
    timezone = db.Column(
        TimezoneType(backend="pytz"),
        default=pytz_timezone(config.DEFAULT_TIMEZONE),
    )
    locale = db.Column(LocaleType, default=Locale("en", "US"))
    data = db.Column(JSONB)
    role = db.Column(db.String(30), default="user")
    has_avatar = db.Column(db.Boolean(), default=False)

    notifications_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_userid = db.Column(db.String(60), default="")
    notifications_mattermost_enabled = db.Column(db.Boolean(), default=False)
    notifications_mattermost_userid = db.Column(db.String(60), default="")
    notifications_discord_enabled = db.Column(db.Boolean(), default=False)
    notifications_discord_userid = db.Column(db.String(60), default="")

    departments = db.relationship("Department", secondary=department_link)

    def __repr__(self):
        if sys.version_info[0] < 3:
            return "<Person %s>" % self.full_name().encode("utf-8")
        else:
            return "<Person %s>" % self.full_name()

    def full_name(self):
        return "%s %s" % (self.first_name, self.last_name)

    def serialize(self, obj_type="Person", relations=False):
        data = SerializerMixin.serialize(self, "Person", relations=relations)
        data["full_name"] = self.full_name()
        return data

    def serialize_safe(self, relations=False):
        data = SerializerMixin.serialize(self, "Person", relations=relations)
        data["full_name"] = self.full_name()
        del data["password"]
        return data

    def present_minimal(self, relations=False):
        data = SerializerMixin.serialize(self, "Person", relations=relations)
        return {
            "id": data["id"],
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "full_name": self.full_name(),
            "has_avatar": data["has_avatar"],
            "active": data["active"],
            "departments": data["departments"],
        }

    def set_departments(self, department_ids):
        from zou.app.models.department import Department

        self.departments = []
        for department_id in department_ids:
            department = Department.get(department_id)
            if department is not None:
                self.departments.append(department)
        self.save()

    @classmethod
    def create_from_import(cls, person):
        del person["type"]
        del person["full_name"]
        is_update = False
        previous_person = cls.get(person["id"])

        if "password" in person:
            person["password"] = person["password"].encode()

        department_ids = None
        if "departments" in person:
            department_ids = person.pop("departments", None)

        if previous_person is None:
            previous_person = cls.create(**person)
        else:
            is_update = True
            previous_person.update(person)

        if department_ids is not None:
            previous_person.set_departments(department_ids)

        return (previous_person, is_update)
