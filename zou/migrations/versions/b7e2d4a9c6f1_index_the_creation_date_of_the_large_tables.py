"""index the creation date of the large tables

The lists walked by cursor come newest created first, the id settling
the order of rows created together. Without an index on both columns,
every request of a walk sorts the whole table.

Revision ID: b7e2d4a9c6f1
Revises: e74cbce89021
Create Date: 2026-11-10 16:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e2d4a9c6f1"
down_revision = "e74cbce89021"
branch_labels = None
depends_on = None

TABLES = [
    "api_event",
    "comment",
    "entity",
    "news",
    "notification",
    "preview_file",
    "task",
    "time_spent",
]


def upgrade():
    # These are the largest tables of an instance: the indexes are built
    # concurrently so that writes go on during the migration.
    # Caveat: if a concurrent build is interrupted, Postgres keeps an
    # INVALID index that if_not_exists will skip on retry; drop it
    # manually (check pg_index.indisvalid) before re-running.
    with op.get_context().autocommit_block():
        for table in TABLES:
            op.create_index(
                f"ix_{table}_created_at_id",
                table,
                ["created_at", "id"],
                unique=False,
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade():
    with op.get_context().autocommit_block():
        for table in reversed(TABLES):
            op.drop_index(
                f"ix_{table}_created_at_id",
                table_name=table,
                postgresql_concurrently=True,
                if_exists=True,
            )
