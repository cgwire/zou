"""empty message

Revision ID: 389cfb9de776
Revises: a65bdadbae2f
Create Date: 2019-02-05 18:43:19.270283

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "389cfb9de776"
down_revision = "a65bdadbae2f"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "task", sa.Column("last_comment_date", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "task", sa.Column("retake_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "task_status", sa.Column("is_retake", sa.Boolean(), nullable=True)
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("task_status", "is_retake")
    op.drop_column("task", "retake_count")
    op.drop_column("task", "last_comment_date")
    # ### end Alembic commands ###