from sqlalchemy_utils import (
    UUIDType,
    EmailType,
    LocaleType,
    TimezoneType,
    ChoiceType,
)
from sqlalchemy import Index
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import JSONB

from pytz import timezone as pytz_timezone
from babel import Locale

from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.models.department import Department
from zou.app import config, db


TWO_FACTOR_AUTHENTICATION_TYPES = [
    ("totp", "TOTP"),
    ("email_otp", "Email OTP"),
    ("fido", "FIDO"),
]

CONTRACT_TYPES = [
    ("open-ended", "Open-ended"),
    ("fixed-term", "Fixed-term"),
    ("short-term", "Short-term"),
    ("freelance", "Freelance"),
    ("apprentice", "Apprentice"),
    ("internship", "Internship"),
]

ROLE_TYPES = [
    ("user", "Artist"),
    ("admin", "Studio Manager"),
    ("supervisor", "Supervisor"),
    ("manager", "Production Manager"),
    ("client", "Client"),
    ("vendor", "Vendor"),
]


class DepartmentLink(db.Model):
    __tablename__ = "department_link"
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
    )
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        primary_key=True,
    )


class Person(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a member of the studio (and an API user).
    """

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(EmailType)
    phone = db.Column(db.String(30))
    contract_type = db.Column(
        ChoiceType(CONTRACT_TYPES), default="open-ended", nullable=False
    )

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
    role = db.Column(ChoiceType(ROLE_TYPES), default="user", nullable=False)
    has_avatar = db.Column(db.Boolean(), default=False)

    notifications_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_userid = db.Column(db.String(60), default="")
    notifications_mattermost_enabled = db.Column(db.Boolean(), default=False)
    notifications_mattermost_userid = db.Column(db.String(60), default="")
    notifications_discord_enabled = db.Column(db.Boolean(), default=False)
    notifications_discord_userid = db.Column(db.String(60), default="")

    is_bot = db.Column(db.Boolean(), default=False, nullable=False)
    jti = db.Column(db.String(60), nullable=True, unique=True)
    expiration_date = db.Column(db.Date(), nullable=True)

    departments = db.relationship(
        "Department", secondary="department_link", lazy="joined"
    )
    studio_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("studio.id"), index=True
    )

    is_generated_from_ldap = db.Column(db.Boolean(), default=False)
    ldap_uid = db.Column(db.String(60), unique=True, default=None)

    __table_args__ = (
        Index(
            "only_one_email_by_person",
            email,
            is_bot,
            unique=True,
            postgresql_where=is_bot.isnot(True),
        ),
    )

    def __repr__(self):
        return f"<Person {self.full_name}>"

    @hybrid_property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        else:
            return f"{self.first_name}{self.last_name}"

    @full_name.expression
    def full_name(cls):
        if cls.first_name and cls.last_name:
            return cls.first_name + " " + cls.last_name
        else:
            return cls.first_name + cls.last_name

    def fido_devices(self):
        if self.fido_credentials is None:
            return []
        else:
            return [
                credential["device_name"]
                for credential in self.fido_credentials
            ]

    def serialize(
        self, obj_type="Person", relations=False, milliseconds=False
    ):
        data = SerializerMixin.serialize(
            self, obj_type, relations=relations, milliseconds=milliseconds
        )
        data["fido_devices"] = self.fido_devices()
        return data

    def serialize_safe(self, relations=False, milliseconds=False):
        data = self.serialize(relations=relations, milliseconds=milliseconds)
        del data["password"]
        del data["totp_secret"]
        del data["email_otp_secret"]
        del data["otp_recovery_codes"]
        del data["fido_credentials"]
        del data["jti"]
        return data

    def present_minimal(self, relations=False, milliseconds=False):
        data = SerializerMixin.serialize(
            self, "Person", relations=relations, milliseconds=milliseconds
        )
        return {
            "id": data["id"],
            "first_name": data["first_name"],
            "last_name": data["last_name"],
            "full_name": self.full_name,
            "has_avatar": data["has_avatar"],
            "active": data["active"],
            "departments": data.get("departments", []),
            "studio_id": data["studio_id"],
            "role": data["role"],
            "desktop_login": data["desktop_login"],
            "is_bot": data["is_bot"],
        }

    def set_departments(self, department_ids):
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
