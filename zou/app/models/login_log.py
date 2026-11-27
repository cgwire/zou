from sqlalchemy_utils import ChoiceType, IPAddressType, UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin

ORIGINS = [("web", "Web"), ("script", "Script")]


class LoginLog(db.Model, BaseMixin, SerializerMixin):
    """
    This table logs all the logins of web sessions. Its aim is to make a table
    that helps to find suspicious behaviours.
    """

    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        nullable=False,
        index=True,
    )
    ip_address = db.Column(IPAddressType)
    origin = db.Column(ChoiceType(ORIGINS))
