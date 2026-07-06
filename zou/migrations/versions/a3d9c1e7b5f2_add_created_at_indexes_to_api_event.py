"""add created_at indexes to api_event

Revision ID: a3d9c1e7b5f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-06 09:20:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3d9c1e7b5f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    # The event log is always read sorted by creation date, optionally
    # filtered by project. api_event can be huge, so build the indexes
    # concurrently to avoid locking writes during the migration.
    # Caveat: if a concurrent build is interrupted, Postgres keeps an
    # INVALID index that if_not_exists will skip on retry; drop it
    # manually (check pg_index.indisvalid) before re-running.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_api_event_created_at",
            "api_event",
            ["created_at"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_api_event_project_id_created_at",
            "api_event",
            ["project_id", "created_at"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_api_event_project_id_created_at",
            table_name="api_event",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_api_event_created_at",
            table_name="api_event",
            postgresql_concurrently=True,
            if_exists=True,
        )
