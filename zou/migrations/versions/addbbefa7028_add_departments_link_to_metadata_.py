"""add departments link to metadata descriptor

Revision ID: addbbefa7028
Revises: 29fe01a6c9eb
Create Date: 2022-04-08 14:12:58.884338

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "addbbefa7028"
down_revision = "29fe01a6c9eb"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "department_metadata_descriptor_link",
        sa.Column(
            "metadata_descriptor_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=True,
        ),
        sa.Column(
            "department_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
        ),
        sa.ForeignKeyConstraint(
            ["metadata_descriptor_id"],
            ["metadata_descriptor.id"],
        ),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("department_metadata_descriptor_link")
    # ### end Alembic commands ###
