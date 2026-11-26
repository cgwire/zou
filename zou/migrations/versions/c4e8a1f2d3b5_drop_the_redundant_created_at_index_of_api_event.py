"""drop the redundant created_at index of api_event

ix_api_event_created_at_id starts with created_at, so it serves every
query that ix_api_event_created_at served.

Revision ID: c4e8a1f2d3b5
Revises: 5861a2712a56
Create Date: 2026-11-26 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4e8a1f2d3b5"
down_revision = "5861a2712a56"
branch_labels = None
depends_on = None


def upgrade():
    # An interrupted concurrent build leaves ix_api_event_created_at_id
    # INVALID. Then keep the old index: it is the only one that serves
    # the sort on created_at.
    is_valid = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = "
                "to_regclass('ix_api_event_created_at_id')"
            )
        )
        .scalar()
    )
    if not is_valid:
        return
    # api_event can be huge: drop the index concurrently, so that writes
    # are not locked during the migration.
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_api_event_created_at",
            table_name="api_event",
            postgresql_concurrently=True,
            if_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_api_event_created_at",
            "api_event",
            ["created_at"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )
