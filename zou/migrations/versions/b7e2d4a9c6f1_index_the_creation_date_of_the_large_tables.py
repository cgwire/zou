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
    "comment",
    "entity",
    "notification",
    "preview_file",
    "task",
    "time_spent",
]


def upgrade():
    for table in TABLES:
        op.create_index(
            f"ix_{table}_created_at_id",
            table,
            ["created_at", "id"],
            unique=False,
        )


def downgrade():
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_created_at_id", table_name=table)
