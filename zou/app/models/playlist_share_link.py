from sqlalchemy_utils import UUIDType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class PlaylistShareLink(db.Model, BaseMixin, SerializerMixin):
    """
    Map a random token to a playlist, allowing external users to access
    and comment on it without a Kitsu account.
    """

    token = db.Column(
        db.String(64), unique=True, nullable=False, index=True
    )
    playlist_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("playlist.id"),
        nullable=False,
        index=True,
    )
    created_by = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("person.id"),
        nullable=False,
    )
    expiration_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean(), default=True, nullable=False)
    can_comment = db.Column(db.Boolean(), default=True, nullable=False)
    password = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.Index(
            "ix_playlist_share_link_playlist_active",
            "playlist_id",
            "is_active",
        ),
    )
