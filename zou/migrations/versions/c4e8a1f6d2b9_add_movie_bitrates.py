"""Add movie encoding bitrates to task type links

Revision ID: c4e8a1f6d2b9
Revises: a3f7c2d91b45
Create Date: 2026-09-15 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "c4e8a1f6d2b9"
down_revision = "a3f7c2d91b45"
branch_labels = None
depends_on = None

TABLES = ("project_task_type_link", "project_template_task_type_link")


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "hd_bitrate_compression", sa.Integer(), nullable=True
                )
            )
            batch_op.add_column(
                sa.Column(
                    "ld_bitrate_compression", sa.Integer(), nullable=True
                )
            )


def downgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("ld_bitrate_compression")
            batch_op.drop_column("hd_bitrate_compression")
