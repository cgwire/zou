from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin


class WorkingFileCreateRequest(db.Model, BaseMixin):
    """
    Record an idempotency key for a created WorkingFile.
    """

    task_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
    )
    request_id = db.Column(UUIDType(binary=False), nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    working_file_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("working_file.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "task_id",
            "person_id",
            "request_id",
            name="working_file_create_request_uc",
        ),
    )
