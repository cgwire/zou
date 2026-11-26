import logging

from babel import Locale
from babel.core import UnknownLocaleError
from pytz import timezone as pytz_timezone
from sqlalchemy import Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy_utils import (
    ChoiceType,
    EmailType,
    LocaleType,
    TimezoneType,
    UUIDType,
)

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.department import Department
from zou.app.models.serializer import SerializerMixin
from zou.app.stores import config_store
from zou.app.utils import fields

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

DISPLAY_DATE_FORMATS = [
    "YYYY-MM-DD",
    "DD/MM/YYYY",
    "MM/DD/YYYY",
]

SENSITIVE_FIELDS = [
    "password",
    "totp_secret",
    "email_otp_secret",
    "otp_recovery_codes",
    "fido_credentials",
    "fido_devices",
    "jti",
    # Lockout state. serialize_safe showed how far each account was in its
    # login burst. Because the columns were filterable, they also showed who is
    # locked now. An admin can still clear it: this does not affect writes.
    "login_failed_attemps",
    "last_login_failed",
    # The identities that an account uses to sign in through SSO. Only the
    # callbacks, and an admin who unlinks an account, use them.
    "oidc_issuer",
    "oidc_subject",
    "saml_issuer",
    "saml_subject",
]

# The two-factor settings: only the auth routes change them.
TWO_FACTOR_FIELDS = [
    "totp_enabled",
    "totp_secret",
    "email_otp_enabled",
    "email_otp_secret",
    "fido_enabled",
    "fido_credentials",
    "otp_recovery_codes",
    "preferred_two_factor_authentication",
]


def normalize_country(value):
    """
    Normalize an ISO 3166-1 alpha-2 country code to its canonical uppercase
    form. Return an ``(is_valid, normalized)`` tuple:

      - ``(True, "FR")`` for a valid two-letter code, with any case or
        whitespace;
      - ``(True, None)`` for an empty or ``None`` value ("no country");
      - ``(False, None)`` for a malformed value: a wrong length, characters
        that are not ASCII or not letters, or an input that is not a string,
        such as a single-element list from SAML.

    These callers use this function as their single source of truth:

      - the API guard, which raises 400 if the value is not valid;
      - the CSV import, which fails the row;
      - the SSO sign-in, which drops the value;
      - the model validator, which discards the value without an error.
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
    Normalize a locale to a name that Python Babel can parse back. Return an
    ``(is_valid, normalized)`` tuple:

      - ``(True, "en_US")`` for a locale that Babel recognizes, with any case
        and surrounding whitespace. The function trims the value, but does not
        change it to the canonical form of Babel. Thus ``zh_CN`` does not
        become ``zh_Hans_CN``, and the value stays in the column width;
      - ``(True, None)`` for an empty or ``None`` value ("no locale");
      - ``(False, None)`` for a value that Babel cannot parse (an unknown
        locale, a malformed identifier, or an input that is not a string, such
        as a single-element list from SAML), or for a value too long for the
        column.

    Two callers use this function as their single source of truth: the API
    guard (it raises 400 if the value is not valid) and the model validator (it
    discards the value without an error). Without this function, Zou stores an
    unparseable value as it is. Then each later read of the person fails,
    because LocaleType parses the stored column value again through Babel on
    load.
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
    # The locale column is a Unicode(10). A longer value overflows the column,
    # even if Babel accepts it (for example the "en_US_POSIX" variant).
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
    A person is a member of the studio (and an API user).
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
    use_12_hour_clock = db.Column(db.Boolean(), default=False)
    display_date_format = db.Column(db.String(20), default="YYYY-MM-DD")
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
    preview_project_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project.id"),
        nullable=True,
        unique=True,
        index=True,
    )
    preview_opened_at = db.Column(db.DateTime, nullable=True)
    preview_open_until = db.Column(db.DateTime, nullable=True)
    jti = db.Column(db.String(60), nullable=True, unique=True)
    expiration_date = db.Column(db.Date(), nullable=True)
    is_generated_from_ldap = db.Column(db.Boolean(), default=False)
    ldap_uid = db.Column(db.String(60), unique=True, default=None)
    oidc_issuer = db.Column(db.Text(), nullable=True)
    oidc_subject = db.Column(db.String(255), nullable=True)
    saml_issuer = db.Column(db.Text(), nullable=True)
    saml_subject = db.Column(db.String(255), nullable=True)

    departments = db.relationship(
        "Department",
        secondary=DepartmentLink.__table__,
    )
    studio_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("studio.id"), index=True
    )

    __table_args__ = (
        Index(
            "only_one_email_by_person",
            email,
            is_bot,
            unique=True,
            postgresql_where=is_bot.isnot(True),
        ),
        db.UniqueConstraint(
            "oidc_issuer", "oidc_subject", name="person_oidc_identity_uc"
        ),
        db.UniqueConstraint(
            "saml_issuer", "saml_subject", name="person_saml_identity_uc"
        ),
    )

    def __repr__(self):
        return f"<Person {self.full_name}>"

    @validates("country")
    def validate_country(self, key, value):
        """
        Normalize ISO 3166-1 alpha-2 country codes to their canonical uppercase
        form. Store None for empty or malformed values. The API requests and
        the CSV imports reject these values before this point, with a clear
        error. This validator is the last guard for direct writes (SSO sign-in,
        scripts). It never raises, even if the input is not a string (for
        example a single-element list from a SAML assertion).
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
        Keep only the locales that Python Babel can parse back. Store None for
        empty or malformed values (then the read path uses the default locale).
        The API requests reject these values before this point, with a clear
        400 error. This validator is the last guard for direct writes (SSO
        sign-in, imports, scripts), and it never raises. Without it, Zou stores
        an unparseable value as it is. Then each later read of the person
        fails, because LocaleType parses the stored column again through Babel
        on load.
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
        # concat_ws skips NULL values. nullif changes empty strings to NULL, so
        # that the result matches the Python property for all combinations.
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
            ignored_attrs=SENSITIVE_FIELDS,
            **kwargs,
        )

    def present_minimal(self, relations=False, milliseconds=False):
        """
        Return the minimal dict of the person. Make it directly, not through
        serialize(), because this code runs very often: each comment and each
        reply embeds its author. Include the departments only if relations is
        True.
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
            # Kitsu adds it to the avatar URL as a version.
            "updated_at": fields.serialize_value(
                self.updated_at, milliseconds=milliseconds
            ),
        }

    def present_client(self):
        """
        Return the dict of the person that a client reads: a name and an avatar
        to put on a comment. It shows nothing about the organisation of the
        studio.
        """
        return {
            "id": str(self.id),
            "type": "Person",
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "has_avatar": self.has_avatar,
            "active": self.active,
            "role": fields.serialize_value(self.role),
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
