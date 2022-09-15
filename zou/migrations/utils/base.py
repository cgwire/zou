import datetime

from sqlalchemy_utils import UUIDType
from zou.app.utils import fields
import sqlalchemy as sa


class BaseMixin(object):

    id = sa.Column(
        UUIDType(binary=False), primary_key=True, default=fields.gen_uuid
    )

    # Audit fields
    created_at = sa.Column(sa.DateTime, default=datetime.datetime.utcnow)
    updated_at = sa.Column(
        sa.DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
