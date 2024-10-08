"""Add Entity.is_shared

Revision ID: 59a7445a966c
Revises: ca28796a2a62
Create Date: 2024-08-16 17:31:59.331365

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import expression


# revision identifiers, used by Alembic.
revision = "59a7445a966c"
down_revision = "ca28796a2a62"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("entity", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_shared",
                sa.Boolean(),
                nullable=False,
                server_default=expression.false(),
            )
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("entity", schema=None) as batch_op:
        batch_op.drop_column("is_shared")

    # ### end Alembic commands ###
