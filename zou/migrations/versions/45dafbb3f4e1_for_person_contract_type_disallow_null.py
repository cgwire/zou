"""For person.contract_type disallow null

Revision ID: 45dafbb3f4e1
Revises: 96f58a4a2a58
Create Date: 2024-02-22 15:41:26.682150

"""

from alembic import op
import sqlalchemy as sa
from zou.migrations.utils.base import BaseMixin
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import ChoiceType, EmailType, LocaleType, TimezoneType
from babel import Locale
from pytz import timezone as pytz_timezone
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm.session import Session


# revision identifiers, used by Alembic.
revision = "45dafbb3f4e1"
down_revision = "96f58a4a2a58"
branch_labels = None
depends_on = None

base = declarative_base()

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


class Person(base, BaseMixin):
    """
    Describe a member of the studio (and an API user).
    """

    __tablename__ = "person"
    first_name = sa.Column(sa.String(80), nullable=False)
    last_name = sa.Column(sa.String(80), nullable=False)
    email = sa.Column(EmailType, unique=True)
    phone = sa.Column(sa.String(30))
    contract_type = sa.Column(ChoiceType(CONTRACT_TYPES), default="open-ended")

    active = sa.Column(sa.Boolean(), default=True)
    archived = sa.Column(sa.Boolean(), default=False)
    last_presence = sa.Column(sa.Date())

    password = sa.Column(sa.LargeBinary(60))
    desktop_login = sa.Column(sa.String(80))
    login_failed_attemps = sa.Column(sa.Integer, default=0)
    last_login_failed = sa.Column(sa.DateTime())
    totp_enabled = sa.Column(sa.Boolean(), default=False)
    totp_secret = sa.Column(sa.String(32), default=None)
    email_otp_enabled = sa.Column(sa.Boolean(), default=False)
    email_otp_secret = sa.Column(sa.String(32), default=None)
    fido_enabled = sa.Column(sa.Boolean(), default=False)
    fido_credentials = sa.Column(sa.ARRAY(JSONB))
    otp_recovery_codes = sa.Column(sa.ARRAY(sa.LargeBinary(60)))
    preferred_two_factor_authentication = sa.Column(
        ChoiceType(TWO_FACTOR_AUTHENTICATION_TYPES)
    )

    shotgun_id = sa.Column(sa.Integer, unique=True)
    timezone = sa.Column(
        TimezoneType(backend="pytz"),
        default=pytz_timezone("Europe/Paris"),
    )
    locale = sa.Column(LocaleType, default=Locale("en", "US"))
    data = sa.Column(JSONB)
    role = sa.Column(ChoiceType(ROLE_TYPES), default="user")
    has_avatar = sa.Column(sa.Boolean(), default=False)

    notifications_enabled = sa.Column(sa.Boolean(), default=False)
    notifications_slack_enabled = sa.Column(sa.Boolean(), default=False)
    notifications_slack_userid = sa.Column(sa.String(60), default="")
    notifications_mattermost_enabled = sa.Column(sa.Boolean(), default=False)
    notifications_mattermost_userid = sa.Column(sa.String(60), default="")
    notifications_discord_enabled = sa.Column(sa.Boolean(), default=False)
    notifications_discord_userid = sa.Column(sa.String(60), default="")

    is_bot = sa.Column(sa.Boolean(), default=False, nullable=False)
    jti = sa.Column(sa.String(60), nullable=True, unique=True)
    expiration_date = sa.Column(sa.Date(), nullable=True)


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("person", schema=None) as batch_op:
        session = Session(bind=op.get_bind())
        session.query(Person).update(
            {
                Person.contract_type: "open-ended",
            }
        )
        session.commit()
        batch_op.alter_column(
            "contract_type",
            existing_type=sa.VARCHAR(length=255),
            server_default="open-ended",
            nullable=False,
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.alter_column(
            "contract_type",
            existing_type=sa.VARCHAR(length=255),
            nullable=True,
        )

    # ### end Alembic commands ###
