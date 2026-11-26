"""drop the is_movie column of preview_file

No code reads or writes is_movie: the extension column tells the movie
previews.

Revision ID: d7f3b9e2a6c1
Revises: c4e8a1f2d3b5
Create Date: 2026-11-26 10:05:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7f3b9e2a6c1"
down_revision = "c4e8a1f2d3b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("preview_file", schema=None) as batch_op:
        batch_op.drop_column("is_movie")


def downgrade():
    # The values are gone: the column comes back empty.
    with op.batch_alter_table("preview_file", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_movie", sa.Boolean()))
