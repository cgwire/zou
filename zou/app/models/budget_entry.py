from sqlalchemy_utils import (
    UUIDType,
    ChoiceType,
)
from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.utils import fields

from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES


class BudgetEntry(db.Model, BaseMixin, SerializerMixin):
    """
    Budget entry for a budget. It stores the information about a person
    (present or not) salary for a given department.
    """

    budget_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("budget.id"),
        index=True,
        nullable=False,
    )
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        index=True,
        nullable=False,
    )
    person_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        index=True,
        nullable=True,
    )
    start_date = db.Column(db.Date, nullable=False)
    months_duration = db.Column(db.Integer, nullable=False)
    daily_salary = db.Column(db.Float, nullable=False)
    position = db.Column(ChoiceType(POSITION_TYPES), default="artist")
    seniority = db.Column(ChoiceType(SENIORITY_TYPES), default="mid")
    exceptions = db.Column(JSONB)

    def __repr__(self):
        return "<BudgetEntry of %s - %d %s %s>" % (
            self.budget_id,
            self.department_id,
            self.person_id,
            self.start_date,
        )

    def present(self):
        return fields.serialize_dict(
            {
                "id": self.id,
                "budget_id": self.budget_id,
                "department_id": self.department_id,
                "person_id": self.person_id,
                "start_date": self.start_date,
                "months_duration": self.months_duration,
                "daily_salary": self.daily_salary,
                "position": self.position,
                "seniority": self.seniority,
                "exceptions": self.exceptions,
            }
        )
