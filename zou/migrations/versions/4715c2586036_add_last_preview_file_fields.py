"""add last preview file fields

Revision ID: 4715c2586036
Revises: deeacd38d373
Create Date: 2024-02-06 22:23:19.317612

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "4715c2586036"
down_revision = "deeacd38d373"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_set_preview_automated", sa.Boolean(), nullable=True)
        )

    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "last_preview_file_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                default=uuid.uuid4,
                nullable=True,
            )
        )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("task", schema=None) as batch_op:
        batch_op.drop_column("last_preview_file_id")

    with op.batch_alter_table("project", schema=None) as batch_op:
        batch_op.drop_column("is_set_preview_automated")
    # ### end Alembic commands ###
