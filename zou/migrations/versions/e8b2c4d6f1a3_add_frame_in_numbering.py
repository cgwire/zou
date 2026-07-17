"""Add is_frame_in_numbering to project and project_template

Revision ID: e8b2c4d6f1a3
Revises: c7d3f9b2a1e4
Create Date: 2026-07-17 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "e8b2c4d6f1a3"
down_revision = "c7d3f9b2a1e4"
branch_labels = None
depends_on = None


def upgrade():
    # Default false: the frame counter keeps its classic numbering
    # unless the production opts in.
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_frame_in_numbering",
                    sa.Boolean(),
                    nullable=True,
                    server_default=sa.text("false"),
                )
            )


def downgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("is_frame_in_numbering")
