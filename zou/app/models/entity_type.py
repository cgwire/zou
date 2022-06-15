from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

task_type_link = db.Table(
    "task_type_asset_type_link",
    db.Column(
        "asset_type_id",
        UUIDType(binary=False),
        db.ForeignKey("entity_type.id"),
    ),
    db.Column(
        "task_type_id",
        UUIDType(binary=False),
        db.ForeignKey("task_type.id"),
    ),
)


class EntityType(db.Model, BaseMixin, SerializerMixin):
    """
    Type of entities. It can describe either an asset type, or tell if target
    entity is a shot, sequence, episode or layout scene.
    """

    name = db.Column(db.String(30), unique=True, nullable=False, index=True)
    task_types = db.relationship(
        "TaskType", secondary=task_type_link, lazy="joined"
    )
