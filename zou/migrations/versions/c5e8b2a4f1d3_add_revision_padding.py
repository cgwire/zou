"""Add revision_padding to project and project_template

Revision ID: c5e8b2a4f1d3
Revises: a7d4e2f9c1b8
Create Date: 2026-06-05 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c5e8b2a4f1d3"
down_revision = "a7d4e2f9c1b8"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "revision_padding",
                    sa.Integer(),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )


def downgrade():
    for table in ("project", "project_template"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("revision_padding")
