"""empty message

Revision ID: a65bdadbae2f
Revises: e1ef93f40d3d
Create Date: 2019-01-15 12:19:59.813805

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "a65bdadbae2f"
down_revision = "e1ef93f40d3d"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "metadata_descriptor",
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("field_name", sa.String(length=120), nullable=False),
        sa.Column(
            "choices", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "entity_type", "name", name="metadata_descriptor_uc"
        ),
    )
    op.create_index(
        op.f("ix_metadata_descriptor_entity_type"),
        "metadata_descriptor",
        ["entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_metadata_descriptor_project_id"),
        "metadata_descriptor",
        ["project_id"],
        unique=False,
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(
        op.f("ix_metadata_descriptor_project_id"),
        table_name="metadata_descriptor",
    )
    op.drop_index(
        op.f("ix_metadata_descriptor_entity_type"),
        table_name="metadata_descriptor",
    )
    op.drop_table("metadata_descriptor")
    # ### end Alembic commands ###
