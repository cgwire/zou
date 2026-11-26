from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import expression

from zou.app import db
from zou.app.models.base import BaseMixin
from zou.app.models.serializer import SerializerMixin


class StoredFile(db.Model, BaseMixin, SerializerMixin):
    """
    A registry of the objects in the file storage, with one row for each
    object. A deletion only marks the row (deleted_at). Later, a purge job
    removes the object and sets purged_at. The journal keeps the history of the
    operations on the object. This record is local to the instance: it
    describes the storage of this instance, and Zou never syncs or exposes it.
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
        # purge_forced comes first. Without REMOVE_FILES, the marked rows that
        # are not forced accumulate, and the purge must not read through them.
        db.Index(
            "ix_stored_file_to_purge",
            "purge_forced",
            "deleted_at",
            postgresql_where=db.text(
                "deleted_at IS NOT NULL AND purged_at IS NULL"
            ),
        ),
    )
