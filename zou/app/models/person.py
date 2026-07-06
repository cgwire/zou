import logging

from sqlalchemy_utils import (
    UUIDType,
    EmailType,
    LocaleType,
    TimezoneType,
    ChoiceType,
)
from sqlalchemy import func, Index
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import JSONB

from pytz import timezone as pytz_timezone
from babel import Locale
from babel.core import UnknownLocaleError

from zou.app.models.serializer import SerializerMixin
from zou.app.utils import fields
from zou.app.models.department import Department
from zou.app.models.base import BaseMixin
from zou.app import db
from zou.app.stores import config_store

logger = logging.getLogger(__name__)

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

POSITION_TYPES = [
    ("supervisor", "Supervisor"),
    ("lead", "Lead"),
    ("artist", "Artist"),
]

SENIORITY_TYPES = [
    ("senior", "Senior"),
    ("mid", "Mid"),
    ("junior", "Junior"),
]


def normalize_country(value):
    """
    Normalize an ISO 3166-1 alpha-2 country code to its canonical uppercase
    form. Returns an ``(is_valid, normalized)`` tuple:

      - ``(True, "FR")`` for a valid two-letter code (any casing/whitespace);
      - ``(True, None)`` for an empty or ``None`` value (i.e. "no country");
      - ``(False, None)`` for a malformed value (wrong length, non-ASCII,
        non-alphabetic, or non-string input such as a SAML single-element
        list).

    Single source of truth shared by the API guard (raises 400 on invalid),
    the CSV import (fails the row on invalid) and the model validator
    (silently discards invalid).
    """
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    normalized = value.strip().upper()
    if normalized == "":
        return True, None
    if len(normalized) == 2 and normalized.isascii() and normalized.isalpha():
        return True, normalized
    return False, None


def normalize_locale(value):
    """
    Normalize a locale to a name Python Babel can parse back. Returns an
    ``(is_valid, normalized)`` tuple:

      - ``(True, "en_US")`` for a locale Babel recognizes (any casing and
        surrounding whitespace); the value is trimmed but kept as-is rather
        than re-serialized to Babel's canonical form, so ``zh_CN`` is not
        rewritten to ``zh_Hans_CN`` and stays within the column width;
      - ``(True, None)`` for an empty or ``None`` value (i.e. "no locale");
      - ``(False, None)`` for a value Babel cannot parse (unknown locale,
        malformed identifier, non-string input such as a SAML single-element
        list) or one too long for the column.

    Single source of truth shared by the API guard (raises 400 on invalid)
    and the model validator (silently discards invalid). Without it an
    unparseable value would be stored verbatim and then break every later
    read of the person, since LocaleType re-parses the stored column value
    through Babel on load.
    """
    if value is None:
        return True, None
    if isinstance(value, Locale):
        return True, str(value)
    if not isinstance(value, str):
        return False, None
    normalized = value.strip()
    if normalized == "":
        return True, None
    # The locale column is a Unicode(10); a longer value would overflow the
    # column even if Babel accepts it (e.g. the "en_US_POSIX" variant).
    if len(normalized) > 10:
        return False, None
    try:
        Locale.parse(normalized)
    except (UnknownLocaleError, ValueError, TypeError):
        return False, None
    return True, normalized


class DepartmentLink(db.Model):
    __tablename__ = "department_link"
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        primary_key=True,
        index=True,
    )
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        primary_key=True,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "person_id",
            "department_id",
            name="department_link_uc",
        ),
    )


class Person(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a member of the studio (and an API user).
    """

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(EmailType)
    phone = db.Column(db.String(30))
    country = db.Column(db.String(2))
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
        default=lambda: pytz_timezone(config_store.get_default_timezone()),
    )
    locale = db.Column(
        LocaleType,
        default=lambda: Locale(config_store.get_default_locale()),
    )
    data = db.Column(JSONB)
    role = db.Column(ChoiceType(ROLE_TYPES), default="user", nullable=False)
    position = db.Column(ChoiceType(POSITION_TYPES), default="artist")
    seniority = db.Column(ChoiceType(SENIORITY_TYPES), default="mid")
    daily_salary = db.Column(db.Integer, default=0)

    has_avatar = db.Column(db.Boolean(), default=False)

    notifications_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_enabled = db.Column(db.Boolean(), default=False)
    notifications_slack_userid = db.Column(db.String(60), default="")
    notifications_mattermost_enabled = db.Column(db.Boolean(), default=False)
    notifications_mattermost_userid = db.Column(db.String(60), default="")
    notifications_discord_enabled = db.Column(db.Boolean(), default=False)
    notifications_discord_userid = db.Column(db.String(60), default="")

    is_bot = db.Column(db.Boolean(), default=False, nullable=False)
    is_guest = db.Column(db.Boolean(), default=False, nullable=False)
    jti = db.Column(db.String(60), nullable=True, unique=True)
    expiration_date = db.Column(db.Date(), nullable=True)

    departments = db.relationship(
        "Department",
        secondary=DepartmentLink.__table__,
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

    @validates("country")
    def validate_country(self, key, value):
        """
        Normalize ISO 3166-1 alpha-2 country codes to their canonical
        uppercase form. Empty or malformed values are stored as None. API
        requests and CSV imports are rejected upstream with a clean error;
        this is the last-resort guard for direct writes (SSO sign-in,
        scripts) that never raises, even on non-string input (e.g. a
        single-element list from a SAML assertion).
        """
        is_valid, normalized = normalize_country(value)
        if not is_valid:
            logger.warning(
                f"Discarded invalid country value for person: {value!r}"
            )
        return normalized

    @validates("locale")
    def validate_locale(self, key, value):
        """
        Keep only locales Python Babel can parse back. Empty or malformed
        values are stored as None (the read path then falls back to the
        default locale). API requests are rejected upstream with a clean
        400; this is the last-resort guard for direct writes (SSO sign-in,
        imports, scripts) that never raises. Without it an unparseable value
        would be persisted verbatim and break every later read of the person,
        since LocaleType re-parses the stored column through Babel on load.
        """
        is_valid, normalized = normalize_locale(value)
        if not is_valid:
            logger.warning(
                f"Discarded invalid locale value for person: {value!r}"
            )
        return normalized

    @hybrid_property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        else:
            return f"{self.first_name}{self.last_name}"

    @full_name.expression
    def full_name(cls):
        # The previous form branched on bool(Column), which is always
        # true, and produced NULL as soon as one name part was NULL.
        # concat_ws skips NULLs; nullif maps empty strings to NULL so the
        # result matches the Python property for every combination.
        return func.trim(
            func.concat_ws(
                " ",
                func.nullif(cls.first_name, ""),
                func.nullif(cls.last_name, ""),
            )
        )

    def fido_devices(self):
        if self.fido_credentials is None:
            return []
        else:
            return [
                credential["device_name"]
                for credential in self.fido_credentials
            ]

    def serialize_safe(self, **kwargs):
        return super().serialize(
            ignored_attrs=[
                "password",
                "totp_secret",
                "email_otp_secret",
                "otp_recovery_codes",
                "fido_credentials",
                "fido_devices",
                "jti",
            ],
            **kwargs,
        )

    def present_minimal(self, relations=False, milliseconds=False):
        """
        Build the minimal person dict directly: serializing all columns to
        keep a dozen fields was a hot path (embedded author of every
        comment and reply).
        """
        departments = []
        if relations:
            departments = [
                str(department.id) for department in self.departments
            ]
        return {
            "id": str(self.id),
            "type": "Person",
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "has_avatar": self.has_avatar,
            "active": self.active,
            "departments": departments,
            "studio_id": str(self.studio_id) if self.studio_id else None,
            "role": fields.serialize_value(self.role),
            "desktop_login": self.desktop_login,
            "is_bot": self.is_bot,
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
