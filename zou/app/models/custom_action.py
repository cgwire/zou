from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class CustomAction(db.Model, BaseMixin, SerializerMixin):
    """
    Custom actions are HTTP links that a user can start outside of the API. The
    web frontend mainly uses them, so that a studio can make custom HTTP calls.
    """

    name = db.Column(db.String(80), nullable=False)
    url = db.Column(db.String(400))
    entity_type = db.Column(db.String(40), default="all")
    is_ajax = db.Column(db.Boolean(), default=False)
