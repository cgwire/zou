from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class HardwareItem(db.Model, BaseMixin, SerializerMixin):
    """
    Describes hardware items available in the studio.
    """

    name = db.Column(db.String(40), unique=True, nullable=False)
    short_name = db.Column(db.String(20), nullable=False)
    archived = db.Column(db.Boolean, default=False)
    monthly_cost = db.Column(db.Integer, default=0)
    inventory_amount = db.Column(db.Integer, default=0)
