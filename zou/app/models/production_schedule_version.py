from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy_utils import UUIDType


class ProductionScheduleVersion(db.Model, BaseMixin, SerializerMixin):
    """
    Describe a production schedule.
    """

    name = db.Column(db.String(80), unique=True, nullable=False)
    project_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project.id"),
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


class ProductionScheduleVersionTaskLink(db.Model, BaseMixin, SerializerMixin):
    """
    Link a task to a production schedule version.
    """

    production_schedule_version_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("production_schedule_version.id"),
        primary_key=True,
    )
    task_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task.id"), primary_key=True
    )
    start_date = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)
