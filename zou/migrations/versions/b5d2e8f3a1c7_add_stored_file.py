"""add the stored file table

One row per object written to the file storage. A deletion marks the row
instead of removing the object right away: a purge job removes it later.
The table starts empty and fills as files are written or deleted.

Revision ID: b5d2e8f3a1c7
Revises: a91c4e7d2f65
Create Date: 2026-10-06 10:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b5d2e8f3a1c7"
down_revision = "a91c4e7d2f65"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stored_file",
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("bucket", sa.String(length=20), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("prefix", sa.String(length=40), nullable=False),
        sa.Column("file_id", sa.String(length=200), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "purge_forced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.Column(
            "purge_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "journal",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket", "key", name="stored_file_uc"),
    )
    op.create_index(
        op.f("ix_stored_file_file_id"),
        "stored_file",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        "ix_stored_file_to_purge",
        "stored_file",
        ["purge_forced", "deleted_at"],
        unique=False,
        postgresql_where=sa.text(
            "deleted_at IS NOT NULL AND purged_at IS NULL"
        ),
    )


def downgrade():
    op.drop_index("ix_stored_file_to_purge", table_name="stored_file")
    op.drop_index(op.f("ix_stored_file_file_id"), table_name="stored_file")
    op.drop_table("stored_file")
