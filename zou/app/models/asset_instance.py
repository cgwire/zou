from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class AssetInstance(db.Model, BaseMixin, SerializerMixin):
    """
    An asset instance represents an asset in the given shot or layout scene.
    Use it for complex scenes where an asset needs extra treatments that apply
    only to this shot or layout scene. An asset can have many instances in a
    scene or in a shot (for example, a sword on a battlefield).
    """

    asset_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("entity.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(80))
    number = db.Column(db.Integer())
    description = db.Column(db.String(200))
    active = db.Column(db.Boolean(), default=True)
    data = db.Column(JSONB)

    scene_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("entity.id"), index=True
    )
    target_asset_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("entity.id"), index=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            "asset_id",
            "target_asset_id",
            "scene_id",
            "number",
            name="asset_instance_uc",
        ),
    )

    # Do not use these columns. They are deprecated and a future version will
    # drop them.
    entity_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("entity.id"), index=True
    )
    entity_type_id = db.Column(
        UUIDType(binary=False), db.ForeignKey("entity_type.id"), index=True
    )

    def __repr__(self):
        return f"<AssetInstance {self.id}>"
