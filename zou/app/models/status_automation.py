from sqlalchemy_utils import UUIDType, ChoiceType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

CHANGE_TYPES = [("status", "Status"), ("ready_for", "Ready for")]


class StatusAutomation(db.Model, BaseMixin, SerializerMixin):
    """
    Status automations are entries that allow to describe changes that
    should automatically apply after a task status is changed.

    For instance, a Modeling task set to done will imply to set the Rigging
    task status to ready and the *ready_for* field to be set at Layout.
    """

    entity_type = db.Column(db.String(40), default="asset")

    in_task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    in_task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id"), index=True
    )

    out_field_type = db.Column(
        ChoiceType(CHANGE_TYPES), default="status", nullable=False
    )
    out_task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    out_task_status_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("task_status.id"),
        index=True,
        nullable=True,
    )
    import_last_revision = db.Column(db.Boolean(), default=False)

    archived = db.Column(db.Boolean(), default=False)
