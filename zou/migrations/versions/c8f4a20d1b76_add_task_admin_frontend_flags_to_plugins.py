"""add Task and Project admin frontend flags to plugins

Revision ID: c8f4a20d1b76
Revises: b5d2e8f3a1c7
Create Date: 2026-10-17 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c8f4a20d1b76"
down_revision = "c3e9a7d1f5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "plugin",
        sa.Column(
            "frontend_task_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "plugin",
        sa.Column(
            "frontend_project_admin_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("plugin", "frontend_task_enabled", server_default=None)
    op.alter_column(
        "plugin", "frontend_project_admin_enabled", server_default=None
    )


def downgrade():
    op.drop_column("plugin", "frontend_project_admin_enabled")
    op.drop_column("plugin", "frontend_task_enabled")
