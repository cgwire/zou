from sqlalchemy_utils import UUIDType
from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

department_metadata_descriptor_link = db.Table(
    "department_metadata_descriptor_link",
    db.Column(
        "metadata_descriptor_id",
        UUIDType(binary=False),
        db.ForeignKey("metadata_descriptor.id"),
    ),
    db.Column(
        "department_id", UUIDType(binary=False), db.ForeignKey("department.id")
    ),
)


class MetadataDescriptor(db.Model, BaseMixin, SerializerMixin):
    """
    This models allow to identify which metadata are available for a given
    project and a given entity type.
    """

    project_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("project.id"),
        nullable=False,
        index=True,
    )
    entity_type = db.Column(db.String(60), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    field_name = db.Column(db.String(120), nullable=False)
    choices = db.Column(JSONB)
    for_client = db.Column(db.Boolean(), default=False, index=True)
    departments = db.relationship(
        "Department", secondary=department_metadata_descriptor_link
    )

    __table_args__ = (
        db.UniqueConstraint(
            "project_id", "entity_type", "name", name="metadata_descriptor_uc"
        ),
        db.UniqueConstraint(
            "project_id",
            "entity_type",
            "field_name",
            name="metadata_descriptor_uc2",
        ),
    )

    def __repr__(self):
        return "<MetadataDescriptor %s>" % self.id
