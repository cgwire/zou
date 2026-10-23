"""Add a per-production client allowed override to task status links

Revision ID: f3b8d1a6c4e2
Revises: e5a2c7d9b1f4
Create Date: 2026-10-19 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3b8d1a6c4e2"
down_revision = "e5a2c7d9b1f4"
branch_labels = None
depends_on = None

TABLES = (
    "project_task_status_link",
    "project_template_task_status_link",
)


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("is_client_allowed", sa.Boolean(), nullable=True)
            )


def downgrade():
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("is_client_allowed")
