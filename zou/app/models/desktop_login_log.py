from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class DesktopLoginLog(db.Model, BaseMixin, SerializerMixin):
    """
    This table logs all the logins of desktop sessions. Its aim is to make
    reports that help to validate presence forms.
    """

    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        nullable=False,
        index=True,
    )
    date = db.Column(db.DateTime, nullable=False)
