"""Add is_single_preview_per_revision to project and project_template

Revision ID: a7d4e2f9c1b8
Revises: b3f1a9c2d7e4
Create Date: 2026-06-02 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a7d4e2f9c1b8"
down_revision = "b3f1a9c2d7e4"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "is_single_preview_per_revision",
                    sa.Boolean(),
                    nullable=True,
                    server_default=sa.text("false"),
                )
            )


def downgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("is_single_preview_per_revision")
