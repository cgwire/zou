from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.utils import fields


class Budget(db.Model, BaseMixin, SerializerMixin):
    """
    Budget quote for a project. It's a base object where budget entries
    are linked to.
    """

    project_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("project.id"), index=True
    )
    revision = db.Column(db.Integer, nullable=False, default=1)
    name = db.Column(db.String(255), nullable=False)
    currency = db.Column(db.String(3))

    def __repr__(self):
        return "<Budget of %s - %d %s %s>" % (
            self.project_id,
            self.revision,
            self.name,
            self.id,
        )

    def present(self):
        return fields.serialize_dict(
            {
                "id": self.id,
                "project_id": self.project_id,
                "revision": self.revision,
                "name": self.name,
                "currency": self.currency,
            }
        )
