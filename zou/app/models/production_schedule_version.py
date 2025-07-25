from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy_utils import UUIDType


class ProductionScheduleVersion(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a production schedule.
    """

    name = db.Column(db.String(80), nullable=False)
    project_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    production_schedule_from = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("production_schedule_version.id"),
        index=True,
        nullable=True,
    )
    locked = db.Column(db.Boolean(), default=False)
    canceled = db.Column(db.Boolean(), default=False)
    __table_args__ = (
        db.UniqueConstraint(
            "name", "project_id", name="production_schedule_version_uc"
        ),
    )


class ProductionScheduleVersionTaskLinkPersonLink(db.Model):
    __tablename__ = "production_schedule_version_task_link_person_link"
    production_schedule_version_task_link_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey(
            "production_schedule_version_task_link.id", ondelete="CASCADE"
        ),
        primary_key=True,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProductionScheduleVersionTaskLink(db.Model, BaseMixin, SerializerMixin):
    """
    Link a task to a production schedule version.
    """

    production_schedule_version_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("production_schedule_version.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    start_date = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)
    estimation = db.Column(db.Float, default=0)
    assignees = db.relationship(
        "Person",
        secondary=ProductionScheduleVersionTaskLinkPersonLink.__table__,
    )
    __table_args__ = (
        db.UniqueConstraint(
            "production_schedule_version_id",
            "task_id",
            name="production_schedule_version_task_link_uc",
        ),
    )
