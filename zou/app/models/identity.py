from sqlalchemy_utils import LocaleType, TimezoneType, UUIDType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declared_attr

from pytz import timezone as pytz_timezone
from babel import Locale

from zou.app import db, config
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.utils import fields


class DepartmentLink(db.Model):
    __tablename__ = "department_link"
    id = db.Column(
        UUIDType(binary=False), primary_key=True, default=fields.gen_uuid
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        default=None,
    )
    api_token_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("api_token.id"), default=None
    )
    department_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("department.id"), nullable=False
    )


class Identity(BaseMixin, SerializerMixin):
    """
    Base class for all identity models.
    """

    active = db.Column(db.Boolean(), default=True)
    timezone = db.Column(
        TimezoneType(backend="pytz"),
        default=pytz_timezone(config.DEFAULT_TIMEZONE),
    )
    locale = db.Column(LocaleType, default=Locale("en", "US"))
    data = db.Column(JSONB)
    # TODO: use ChoiceType instead
    role = db.Column(db.String(30), default="user")
    has_avatar = db.Column(db.Boolean(), default=False)

    @declared_attr
    def departments(cls):
        return db.relationship(
            "Department",
            secondary="department_link",
            overlaps="departments",
            lazy="joined",
        )

    def __repr__(self):
        return f"<Identity {self.full_name()}>"

    def full_name(self):
        return f""

    def serialize(self, obj_type="Identity", relations=False):
        data = super().serialize(obj_type, relations=relations)
        data["full_name"] = self.full_name()
        return data

    def serialize_safe(self, relations=False):
        return self.serialize(relations=relations)

    def present_minimal(self, relations=False):
        data = self.serialize(relations=relations)
        return {
            "id": data["id"],
            "full_name": self.full_name(),
            "has_avatar": data["has_avatar"],
            "active": data["active"],
            "departments": data.get("departments", []),
            "role": data["role"],
        }
