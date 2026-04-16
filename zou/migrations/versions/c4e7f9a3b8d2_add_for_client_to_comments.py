"""add for_client flag to comments

Revision ID: c4e7f9a3b8d2
Revises: 8d42b9e1f7a3
Create Date: 2026-04-16 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4e7f9a3b8d2"
down_revision = "8d42b9e1f7a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("comment", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "for_client",
                sa.Boolean(),
                nullable=True,
                server_default=sa.false(),
            )
        )


def downgrade():
    with op.batch_alter_table("comment", schema=None) as batch_op:
        batch_op.drop_column("for_client")
