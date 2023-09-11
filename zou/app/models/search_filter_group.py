from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class SearchFilterGroup(db.Model, BaseMixin, SerializerMixin):
    """
    Groups are used to store search filters into sections.
    """

    list_type = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(80))
    name = db.Column(db.String(200), nullable=False, default="")
    color = db.Column(db.String(8), nullable=False, default="")

    person_id = db.Column(UUIDType(binary=False), db.ForeignKey("person.id"))
    project_id = db.Column(UUIDType(binary=False), db.ForeignKey("project.id"))
