"""add project task type software link

Revision ID: d2f6a8c1e3b7
Revises: d4f1b8a6c2e3
Create Date: 2026-10-16 12:00:00.000000

"""

import uuid

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2f6a8c1e3b7"
down_revision = "d4f1b8a6c2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_task_type_software_link",
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "software_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_type_id"], ["task_type.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["software_id"], ["software.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "task_type_id", "software_id", "id"
        ),
        sa.UniqueConstraint(
            "project_id",
            "task_type_id",
            "software_id",
            name="project_task_type_software_uc",
        ),
    )
    with op.batch_alter_table(
        "project_task_type_software_link", schema=None
    ) as batch_op:
        for column in ["project_id", "task_type_id", "software_id"]:
            batch_op.create_index(
                batch_op.f(f"ix_project_task_type_software_link_{column}"),
                [column],
                unique=False,
            )


def downgrade():
    op.drop_table("project_task_type_software_link")
