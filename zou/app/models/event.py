from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

from sqlalchemy.dialects.postgresql import JSONB


class ApiEvent(db.Model, BaseMixin, SerializerMixin):
    """
    Represent notable events occuring on database (asset creation,
    task assignation, etc.).
    """

    name = db.Column(db.String(80), nullable=False, index=True)
    user_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("person.id"), index=True
    )
    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), index=True
    )
    data = db.Column(JSONB)

    # The event log is always read sorted by creation date, optionally
    # filtered by project, so both access paths need an index.
    __table_args__ = (
        db.Index("ix_api_event_created_at", "created_at"),
        db.Index(
            "ix_api_event_project_id_created_at", "project_id", "created_at"
        ),
    )
