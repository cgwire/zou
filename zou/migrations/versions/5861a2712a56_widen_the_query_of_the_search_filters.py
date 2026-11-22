"""widen the query of the search filters

A search filter of the All Tasks page holds the whole URL query of the
page: a few people picked with every other filter set go past 500
characters.

Revision ID: 5861a2712a56
Revises: b7e2d4a9c6f1
Create Date: 2026-11-17 12:29:30.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5861a2712a56"
down_revision = "b7e2d4a9c6f1"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres widens a varchar without rewriting the table.
    with op.batch_alter_table("search_filter", schema=None) as batch_op:
        batch_op.alter_column(
            "search_query",
            existing_type=sa.String(length=500),
            type_=sa.String(length=5000),
            existing_nullable=False,
        )


def downgrade():
    # The narrow column cannot hold the longer queries, and a cut query
    # would run another search than the one its name tells: they go.
    op.execute(
        "DELETE FROM search_filter WHERE char_length(search_query) > 500"
    )
    with op.batch_alter_table("search_filter", schema=None) as batch_op:
        batch_op.alter_column(
            "search_query",
            existing_type=sa.String(length=5000),
            type_=sa.String(length=500),
            existing_nullable=False,
        )
