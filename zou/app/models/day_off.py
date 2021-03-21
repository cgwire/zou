from sqlalchemy_utils import UUIDType
from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class DayOff(db.Model, BaseMixin, SerializerMixin):
    """
    Tells that someone will have a day off this day.
    """

    date = db.Column(db.Date, nullable=False)
    person_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), index=True
    )
    __table_args__ = (
        db.UniqueConstraint("person_id", "date", name="day_off_uc"),
    )
