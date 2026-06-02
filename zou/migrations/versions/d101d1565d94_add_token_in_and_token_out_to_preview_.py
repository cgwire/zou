"""Add token_in and token_out to preview_file

Revision ID: d101d1565d94
Revises: e7a4c2b9f1d3
Create Date: 2026-05-31 15:38:19.215627

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d101d1565d94"
down_revision = "e7a4c2b9f1d3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("preview_file", schema=None) as batch_op:
        batch_op.add_column(sa.Column("token_in", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("token_out", sa.Integer(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("preview_file", schema=None) as batch_op:
        batch_op.drop_column("token_out")
        batch_op.drop_column("token_in")
