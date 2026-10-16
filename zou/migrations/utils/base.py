import sqlalchemy as sa
from sqlalchemy_utils import UUIDType

from zou.app.utils import date_helpers, fields


class BaseMixin(object):
    id = sa.Column(
        UUIDType(binary=False), primary_key=True, default=fields.gen_uuid
    )

    # Audit fields
    created_at = sa.Column(
        sa.DateTime, default=date_helpers.get_utc_now_datetime
    )
    updated_at = sa.Column(
        sa.DateTime,
        default=date_helpers.get_utc_now_datetime,
        onupdate=date_helpers.get_utc_now_datetime,
    )
