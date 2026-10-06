from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import expression

from zou.app import db
from zou.app.models.serializer import SerializerMixin
from zou.app.models.base import BaseMixin


class StoredFile(db.Model, BaseMixin, SerializerMixin):
    """
    Registry of the objects written to the file storage, one row per
    object. A deletion only marks the row (deleted_at): the object is
    removed later by a purge job, which sets purged_at. The journal keeps
    the history of the operations on the object. Instance-local
    bookkeeping: it describes this instance's storage, it is never synced
    or exposed.
    """

    bucket = db.Column(db.String(20), nullable=False)
    key = db.Column(db.String(255), nullable=False)
    prefix = db.Column(db.String(40), nullable=False)
    file_id = db.Column(db.String(200), nullable=False, index=True)
    size = db.Column(db.BigInteger())
    deleted_at = db.Column(db.DateTime())
    purge_forced = db.Column(
        db.Boolean(),
        default=False,
        server_default=expression.false(),
        nullable=False,
    )
    purged_at = db.Column(db.DateTime())
    purge_attempts = db.Column(
        db.Integer(), default=0, server_default="0", nullable=False
    )
    last_error = db.Column(db.Text())
    journal = db.Column(
        JSONB,
        default=list,
        server_default=db.text("'[]'::jsonb"),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint("bucket", "key", name="stored_file_uc"),
        # purge_forced first: without REMOVE_FILES, the marked rows that
        # are not forced pile up, the purge must not read through them.
        db.Index(
            "ix_stored_file_to_purge",
            "purge_forced",
            "deleted_at",
            postgresql_where=db.text(
                "deleted_at IS NOT NULL AND purged_at IS NULL"
            ),
        ),
    )
