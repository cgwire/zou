"""add person display preferences

Two per-user display preferences surfaced in the Kitsu profile page: an
opt-in 12-hour clock and the date format used for displayed dates. Both
columns are nullable so existing rows keep working; the read paths fall
back to the 24-hour clock and the ISO date format.

Revision ID: c7d3f9b2a1e4
Revises: f2c9a1b7e4d8
Create Date: 2026-07-11 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d3f9b2a1e4"
down_revision = "f2c9a1b7e4d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "person",
        sa.Column("use_12_hour_clock", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "person",
        sa.Column("display_date_format", sa.String(length=20), nullable=True),
    )


def downgrade():
    op.drop_column("person", "display_date_format")
    op.drop_column("person", "use_12_hour_clock")
