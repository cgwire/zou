from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin
from zou.app.models.task_type import TaskType

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
    archived = db.Column(db.Boolean(), default=False)

    @classmethod
    def create_from_import(cls, data):
        is_update = False
        task_types_ids = None
        if "type" in data:
            del data["type"]
        if "task_types" in data:
            task_types_ids = data.pop("task_types", None)
        entity_type = cls.get(data["id"])
        if entity_type is None:
            entity_type = cls.create(**data)
            is_update = False
        else:
            entity_type.update(data)
            is_update = True
        if task_types_ids is not None:
            entity_type.task_types = []
            for task_type_id in task_types_ids:
                task_type = TaskType.get(task_type_id)
                if task_type is not None:
                    entity_type.task_types.append(task_type)
            entity_type.save()
        return (entity_type, is_update)
