from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class TaskTypeAssetTypeLink(db.Model):
    __tablename__ = "task_type_asset_type_link"
    task_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("task_type.id"), primary_key=True
    )
    asset_type_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("entity_type.id"),
        primary_key=True,
    )


class TaskType(db.Model, BaseMixin, SerializerMixin):
    """
    Categorize tasks in domain areas: modeling, animation, etc.
    """

    name = db.Column(db.String(40), nullable=False)
    short_name = db.Column(db.String(20))
    color = db.Column(db.String(7), default="#FFFFFF")
    priority = db.Column(db.Integer, default=1)
    for_shots = db.Column(db.Boolean, default=False)  # deprecated
    for_entity = db.Column(db.String(30), default="Asset")
    allow_timelog = db.Column(db.Boolean, default=True)
    shotgun_id = db.Column(db.Integer, index=True)

    department_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("department.id")
    )

    asset_types = db.relationship(
        "EntityType", secondary="task_type_asset_type_link"
    )

    __table_args__ = (
        db.UniqueConstraint(
            "name", "for_entity", "department_id", name="task_type_uc"
        ),
    )

    # def set_asset_types(self, asset_type_ids):
    #     return self.set_links(
    #         asset_type_ids, TaskTypeAssetTypeLink, "task_type_id", "asset_type_id"
    #     )
