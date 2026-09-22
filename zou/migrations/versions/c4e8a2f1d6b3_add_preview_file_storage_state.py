"""add the preview file storage state table

One row per stored file of a preview file (bucket and prefix): present,
confirmed missing, or failed to be generated. The table starts empty and
fills as files are written and read, or through probe-preview-files.

Revision ID: c4e8a2f1d6b3
Revises: a3f7c2d91b45
Create Date: 2026-09-22 12:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a2f1d6b3"
down_revision = "a3f7c2d91b45"
branch_labels = None
depends_on = None

STORAGE_STATES = [
    ("ok", "Ok"),
    ("missing", "Missing"),
    ("failed", "Failed"),
]


def upgrade():
    op.create_table(
        "preview_file_storage_state",
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "preview_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(length=20), nullable=False),
        sa.Column("prefix", sa.String(length=40), nullable=False),
        sa.Column(
            "state",
            sqlalchemy_utils.types.choice.ChoiceType(STORAGE_STATES),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["preview_file_id"], ["preview_file.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "preview_file_id",
            "bucket",
            "prefix",
            name="preview_file_storage_state_uc",
        ),
    )
    op.create_index(
        op.f("ix_preview_file_storage_state_preview_file_id"),
        "preview_file_storage_state",
        ["preview_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_preview_file_storage_state_bucket_prefix_state",
        "preview_file_storage_state",
        ["bucket", "prefix", "state"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_preview_file_storage_state_bucket_prefix_state",
        table_name="preview_file_storage_state",
    )
    op.drop_index(
        op.f("ix_preview_file_storage_state_preview_file_id"),
        table_name="preview_file_storage_state",
    )
    op.drop_table("preview_file_storage_state")
