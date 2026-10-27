"""Add the upload date of the working files and the output files

Revision ID: c7d2e9f4a1b3
Revises: b8e3d1f6a2c9
Create Date: 2026-10-28 01:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d2e9f4a1b3"
down_revision = "b8e3d1f6a2c9"
branch_labels = None
depends_on = None

TABLES = ("working_file", "output_file")


def upgrade():
    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("uploaded_at", sa.DateTime(), nullable=True)
            )


def downgrade():
    for table in reversed(TABLES):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("uploaded_at")
