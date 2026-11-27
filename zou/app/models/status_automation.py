from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import ChoiceType, UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin

CHANGE_TYPES = [("status", "Status"), ("ready_for", "Ready for")]


def build_simple_trigger(task_type_id, task_status_id):
    """
    Return the trigger of the legacy single condition. If one of its two values
    is missing, return None.
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
    A status automation describes changes that Zou applies automatically after
    a change of task status.

    The trigger (``in_conditions``) is a group. It has an operator (``and`` or
    ``or``) and conditions. Each condition is a task type and the statuses that
    meet it. For example, if the Lighting and FX tasks go to done, Zou sets the
    Compositing task status to ready. If a Modeling task goes to done, Zou sets
    the *ready_for* field to Layout. A status change can apply only to target
    tasks in the given statuses (``out_only_if_task_status_ids``).

    ``in_task_type_id`` and ``in_task_status_id`` are deprecated. If the
    trigger has one condition with one status, the server keeps them as a
    mirror of it. If not, they are null.
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
        # If the instance is older than the trigger groups, its sync sends only
        # the legacy columns.
        if data.get("in_conditions") is None:
            data["in_conditions"] = build_simple_trigger(
                data.get("in_task_type_id"), data.get("in_task_status_id")
            )
        return super().create_from_import(data)
