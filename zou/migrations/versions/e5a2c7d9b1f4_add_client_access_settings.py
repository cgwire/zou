"""Add client access settings to projects and task type links

Revision ID: e5a2c7d9b1f4
Revises: d2f6a8c1e3b7
Create Date: 2026-10-19 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5a2c7d9b1f4"
down_revision = "d2f6a8c1e3b7"
branch_labels = None
depends_on = None

PROJECT_COLUMNS = (
    "is_client_stats_visible",
    "is_client_task_list_visible",
    "is_client_task_panel_visible",
)
LINK_COLUMN = "is_client_visible"


def _column(name):
    return sa.Column(
        name, sa.Boolean(), nullable=True, server_default=sa.text("true")
    )


def upgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            for name in PROJECT_COLUMNS:
                batch_op.add_column(_column(name))
    for table in (
        "project_task_type_link",
        "project_template_task_type_link",
    ):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(_column(LINK_COLUMN))


def downgrade():
    for table in (
        "project_template_task_type_link",
        "project_task_type_link",
    ):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column(LINK_COLUMN)
    for table in ("project_template", "project"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            for name in PROJECT_COLUMNS:
                batch_op.drop_column(name)
