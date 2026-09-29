from sqlalchemy_utils import UUIDType, ChoiceType

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin

STORAGE_STATES = [
    ("ok", "Ok"),
    ("missing", "Missing"),
    ("failed", "Failed"),
]


class PreviewFileStorageState(db.Model, BaseMixin, SerializerMixin):
    """
    State of one stored file of a preview file: present, confirmed
    missing, or failed to be generated. Instance-local bookkeeping: it
    describes this instance's storage, it is never synced or exposed.
    """

    preview_file_id = db.Column(
        UUIDType(binary=False),
        db.ForeignKey("preview_file.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    bucket = db.Column(db.String(20), nullable=False)
    prefix = db.Column(db.String(40), nullable=False)
    state = db.Column(ChoiceType(STORAGE_STATES), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "preview_file_id",
            "bucket",
            "prefix",
            name="preview_file_storage_state_uc",
        ),
        db.Index(
            "ix_preview_file_storage_state_bucket_prefix_state",
            "bucket",
            "prefix",
            "state",
        ),
    )
