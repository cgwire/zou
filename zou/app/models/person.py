from sqlalchemy_utils import (
    UUIDType,
    EmailType,
    LocaleType,
    TimezoneType,
    ChoiceType,
)
from sqlalchemy.dialects.postgresql import JSONB

from pytz import timezone as pytz_timezone
from babel import Locale

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app import config


department_link = db.Table(
    "department_link",
    db.Column(
        "person_id",
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    ),
    db.Column(
        "department_id",
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        primary_key=True,
    ),
)

TWO_FACTOR_AUTHENTICATION_TYPES = [
    ("totp", "TOTP"),
    ("email_otp", "Email OTP"),
    ("fido", "FIDO"),
]


class Person(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a member of the studio (and an API user).
    """

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(EmailType, unique=True)
    phone = db.Column(db.String(30))

    active = db.Column(db.Boolean(), default=True)
    archived = db.Column(db.Boolean(), default=False)
    last_presence = db.Column(db.Date())

    password = db.Column(db.LargeBinary(60))
    desktop_login = db.Column(db.String(80))
    login_failed_attemps = db.Column(db.Integer, default=0)
    last_login_failed = db.Column(db.DateTime())
    totp_enabled = db.Column(db.Boolean(), default=False)
    totp_secret = db.Column(db.String(32), default=None)
    email_otp_enabled = db.Column(db.Boolean(), default=False)
    email_otp_secret = db.Column(db.String(32), default=None)
    fido_enabled = db.Column(db.Boolean(), default=False)
    fido_credentials = db.Column(db.ARRAY(JSONB))
    otp_recovery_codes = db.Column(db.ARRAY(db.LargeBinary(60)))
    preferred_two_factor_authentication = db.Column(
        ChoiceType(TWO_FACTOR_AUTHENTICATION_TYPES)
    )

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

    departments = db.relationship(
        "Department", secondary=department_link, lazy="joined"
    )

    is_generated_from_ldap = db.Column(db.Boolean(), default=False)
    ldap_uid = db.Column(db.String(60), unique=True, default=None)

    def __repr__(self):
        return f"<Person {self.full_name()}>"

    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def fido_devices(self):
        if self.fido_credentials is None:
            return []
        else:
            return [
                credential["device_name"]
                for credential in self.fido_credentials
            ]

    def serialize(self, obj_type="Person", relations=False):
        data = SerializerMixin.serialize(self, "Person", relations=relations)
        data["full_name"] = self.full_name()
        data["fido_devices"] = self.fido_devices()
        return data

    def serialize_safe(self, relations=False):
        data = SerializerMixin.serialize(self, "Person", relations=relations)
        data["full_name"] = self.full_name()
        data["fido_devices"] = self.fido_devices()
        del data["password"]
        del data["totp_secret"]
        del data["email_otp_secret"]
        del data["otp_recovery_codes"]
        del data["fido_credentials"]
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
            "departments": data.get("departments", []),
            "role": data["role"],
            "desktop_login": data["desktop_login"],
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

        if "password" in person and person["password"] is not None:
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
