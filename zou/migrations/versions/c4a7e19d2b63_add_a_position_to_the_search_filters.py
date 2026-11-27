"""add a position to the search filters

A user orders the saved searches and their groups. A row with no position
stays in the alphabetical order, after the ordered rows.

Revision ID: c4a7e19d2b63
Revises: d7f3b9e2a6c1
Create Date: 2026-11-26 17:20:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4a7e19d2b63"
down_revision = "d7f3b9e2a6c1"
branch_labels = None
depends_on = None


def upgrade():
    for table in ["search_filter", "search_filter_group"]:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("position", sa.Integer(), nullable=True)
            )


def downgrade():
    for table in ["search_filter", "search_filter_group"]:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("position")
