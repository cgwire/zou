from sqlalchemy_utils import UUIDType, ChoiceType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.utils import fields

MILESTONE_TYPES = [
    ("kickoff", "Kickoff"),
    ("review", "Review"),
    ("approval", "Approval"),
    ("delivery", "Delivery"),
    ("other", "Other"),
]

MILESTONE_STATUSES = [
    ("todo", "Todo"),
    ("wfa", "Waiting For Approval"),
    ("done", "Done"),
]


class Milestone(db.Model, BaseMixin, SerializerMixin):
    """
    Allow to set a milestone date to the production schedule.
    """

    date = db.Column(db.Date())
    name = db.Column(db.String(40), nullable=False)
    color = db.Column(db.String(7))
    milestone_type = db.Column(
        ChoiceType(MILESTONE_TYPES), default="other", nullable=False
    )
    status = db.Column(
        ChoiceType(MILESTONE_STATUSES), default="todo", nullable=False
    )

    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), index=True
    )
    task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), index=True
    )

    def present(self):
        return fields.serialize_dict(
            {
                "id": self.id,
                "date": self.date,
                "name": self.name,
                "color": self.color,
                "milestone_type": self.milestone_type,
                "status": self.status,
                "project_id": self.project_id,
                "task_type_id": self.task_type_id,
            }
        )
