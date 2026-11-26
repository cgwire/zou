from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class OutputType(db.Model, BaseMixin, SerializerMixin):
    """
    The type of an output file (geometry, cache, etc.).
    """

    name = db.Column(db.String(40), unique=True, nullable=False, index=True)
    short_name = db.Column(db.String(20), nullable=False)
