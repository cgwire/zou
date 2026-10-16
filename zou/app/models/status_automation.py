from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import ChoiceType, UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin

CHANGE_TYPES = [("status", "Status"), ("ready_for", "Ready for")]


def build_simple_trigger(task_type_id, task_status_id):
    """
    Return the trigger of the legacy single condition, or None when one of
    its two values is missing.
    """
    if task_type_id is None or task_status_id is None:
        return None
    return {
        "operator": "and",
        "conditions": [
            {
                "task_type_id": str(task_type_id),
                "task_status_ids": [str(task_status_id)],
            }
        ],
    }


class StatusAutomation(db.Model, BaseMixin, SerializerMixin):
    """
    Status automations are entries that allow to describe changes that
    should automatically apply after a task status is changed.

    The trigger (``in_conditions``) is a group: an operator, ``and`` or
    ``or``, and conditions, each one a task type and the statuses that meet
    it. For instance, Lighting and FX tasks set to done imply to set the
    Compositing task status to ready, and a Modeling task set to done
    implies to set the *ready_for* field to Layout. A status change can be
    limited to target tasks in given statuses
    (``out_only_if_task_status_ids``).

    ``in_task_type_id`` and ``in_task_status_id`` are deprecated: the server
    keeps them as a mirror of a trigger made of one condition with one
    status, and null otherwise.
    """

    entity_type = db.Column(db.String(40), default="asset")

    in_task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    in_task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id"), index=True
    )
    in_conditions = db.Column(JSONB, nullable=True)

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
    out_only_if_task_status_ids = db.Column(JSONB, nullable=True)
    import_last_revision = db.Column(db.Boolean(), default=False)

    archived = db.Column(db.Boolean(), default=False)

    @classmethod
    def create_from_import(cls, data):
        # A sync from an instance older than the trigger groups only
        # carries the legacy columns.
        if data.get("in_conditions") is None:
            data["in_conditions"] = build_simple_trigger(
                data.get("in_task_type_id"), data.get("in_task_status_id")
            )
        return super().create_from_import(data)
