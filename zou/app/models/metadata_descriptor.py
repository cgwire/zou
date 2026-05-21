from sqlalchemy_utils import UUIDType, ChoiceType
from sqlalchemy.dialects.postgresql import JSONB

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.models.department import Department


class DepartmentMetadataDescriptorLink(db.Model):
    metadata_descriptor_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("metadata_descriptor.id"),
        index=True,
        primary_key=True,
    )
    department_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("department.id"),
        index=True,
        primary_key=True,
    )

    __table_args__ = (
        db.UniqueConstraint(
            "metadata_descriptor_id",
            "department_id",
            name="department_metadata_descriptor_link_uc",
        ),
    )


METADATA_DESCRIPTOR_TYPES = [
    ("string", "String"),
    ("number", "Number"),
    ("list", "List"),
    ("taglist", "Taglist"),
    ("boolean", "Boolean"),
    ("checklist", "Checklist"),
]


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
    data_type = db.Column(ChoiceType(METADATA_DESCRIPTOR_TYPES))
    field_name = db.Column(db.String(120), nullable=False)
    choices = db.Column(JSONB)
    for_client = db.Column(db.Boolean(), default=False, index=True)
    position = db.Column(db.Integer(), nullable=True)
    departments = db.relationship(
        Department,
        secondary=DepartmentMetadataDescriptorLink.__table__,
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
        return f"<MetadataDescriptor {self.id}>"

    def set_departments(self, department_ids):
        return self.set_links(
            department_ids,
            DepartmentMetadataDescriptorLink,
            "metadata_descriptor_id",
            "department_id",
        )

    @classmethod
    def create_from_import(cls, data):
        data.pop("type", None)
        department_ids = data.pop("departments", None)
        previous_data = cls.get(data["id"])
        if previous_data is None:
            instance = cls.create(**data)
            is_update = False
        else:
            previous_data.update(data)
            instance = previous_data
            is_update = True
        if department_ids is not None:
            instance.set_departments(department_ids)
        return instance, is_update
