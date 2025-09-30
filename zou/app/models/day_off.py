from sqlalchemy_utils import UUIDType
from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class DayOff(db.Model, BaseMixin, SerializerMixin):
    """
    Tells that someone will have a day off this day.
    """

    date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text)
    person_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), index=True
    )
    __table_args__ = (
        db.UniqueConstraint("person_id", "date", name="day_off_uc"),
        db.CheckConstraint("date <= end_date", name="day_off_date_check"),
    )

    def serialize_safe(self, **kwargs):
        return self.serialize(ignored_attrs=["description"], **kwargs)
