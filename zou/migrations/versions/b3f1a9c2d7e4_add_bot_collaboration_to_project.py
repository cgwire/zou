"""Add is_bot_collaboration_enabled to project

Revision ID: b3f1a9c2d7e4
Revises: d101d1565d94
Create Date: 2026-05-31 18:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b3f1a9c2d7e4"
down_revision = "d101d1565d94"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_bot_collaboration_enabled",
                sa.Boolean(),
                nullable=True,
                server_default=sa.text("false"),
            )
        )


def downgrade():
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("is_bot_collaboration_enabled")
