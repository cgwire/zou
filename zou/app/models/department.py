from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class HardwareItemDepartmentLink(db.Model, BaseMixin, SerializerMixin):
    """
    A many-to-many link between hardware items and departments. Use it to
    record which departments use which hardware items, for budget forecasts.
    """

    __tablename__ = "hardware_item_department_link"
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        primary_key=True,
        index=True,
    )
    hardware_item_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("hardware_item.id"),
        primary_key=True,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "hardware_item_id",
            "department_id",
            name="hardware_item_department_link_uc",
        ),
    )


class SoftwareDepartmentLink(db.Model, BaseMixin, SerializerMixin):
    """
    A many-to-many link between software and departments. Use it to record
    which departments use which software, for budget forecasts.
    """

    __tablename__ = "software_department_link"
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        primary_key=True,
        index=True,
    )
    software_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("software.id"),
        primary_key=True,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "department_id",
            "software_id",
            name="software_department_link_uc",
        ),
    )


class Department(db.Model, BaseMixin, SerializerMixin):
    """
    A studio department, for example modeling or animation.
    """

    name = db.Column(db.String(80), unique=True, nullable=False)
    color = db.Column(db.String(7), nullable=False)
    archived = db.Column(db.Boolean(), default=False)
