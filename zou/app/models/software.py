from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy.dialects.postgresql import JSONB


class Software(db.Model, BaseMixin, SerializerMixin):
    """
    Describes software used in the studio.
    """

    name = db.Column(db.String(40), unique=True, nullable=False)
    short_name = db.Column(db.String(20), nullable=False)
    archived = db.Column(db.Boolean, default=False)
    version = db.Column(db.String(20), nullable=True)
    file_extension = db.Column(db.String(20), nullable=False)
    secondary_extensions = db.Column(JSONB)
    monthly_cost = db.Column(db.Integer, default=0)
    inventory_amount = db.Column(db.Integer, default=0)
