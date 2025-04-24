from sqlalchemy_utils import UUIDType
from sqlalchemy_utils import ChoiceType

from zou.app.models.person import POSITION_TYPES, SENIORITY_TYPES

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class SalaryScale(db.Model, BaseMixin, SerializerMixin):
    """
    Model to represent a salary scale tied to a department.
    """

    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        index=True,
        nullable=False,
    )

    position = db.Column(ChoiceType(POSITION_TYPES), default="artist")
    seniority = db.Column(ChoiceType(SENIORITY_TYPES), default="mid")
    salary = db.Column(db.Integer, nullable=False, default=0)

    def present(self):
        return self.serialize()
