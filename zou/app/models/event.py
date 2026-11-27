from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class ApiEvent(db.Model, BaseMixin, SerializerMixin):
    """
    This model represents an important event in the database (asset creation,
    task assignment, etc.).
    """

    name = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), index=True
    )
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), index=True
    )
    data = db.Column(JSONB)

    # Readers always sort the event log by creation date, and can filter it by
    # project. Thus each of these two access paths needs an index.
    __table_args__ = (
        db.Index(
            "ix_api_event_project_id_created_at", "project_id", "created_at"
        ),
        db.Index("ix_api_event_created_at_id", "created_at", "id"),
    )
