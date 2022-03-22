from sqlalchemy_utils import UUIDType
from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

class StatusAutomation(db.Model, BaseMixin, SerializerMixin):
    """
    Status automations are status changes automations.
    They allow supervisors to automate status changes or `ready for` set when 
    a status of a task is changed.
    """
    entity_type = db.Column(db.String(40), default="asset")

    in_field_type = db.Column(db.String(40), default="status")  # TODO maybe to delete
    in_task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    in_task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id"), index=True
    )

    out_field_type = db.Column(db.String(40), default="status")
    out_task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )
    out_task_status_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_status.id"), index=True, nullable=True
    )
