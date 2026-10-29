"""add WorkingFile create idempotency records

Revision ID: f9a1c2e3d4b5
Revises: b8e3d1f6a2c9
Create Date: 2026-10-29 15:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

revision = "f9a1c2e3d4b5"
down_revision = "b8e3d1f6a2c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "working_file_create_request",
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "working_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["task.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["person.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["working_file_id"],
            ["working_file.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "person_id",
            "request_id",
            name="working_file_create_request_uc",
        ),
        sa.UniqueConstraint(
            "working_file_id",
            name="working_file_create_request_working_file_uc",
        ),
    )
    op.create_index(
        "ix_working_file_create_request_task_id",
        "working_file_create_request",
        ["task_id"],
    )
    op.create_index(
        "ix_working_file_create_request_person_id",
        "working_file_create_request",
        ["person_id"],
    )


def downgrade():
    op.drop_index(
        "ix_working_file_create_request_person_id",
        table_name="working_file_create_request",
    )
    op.drop_index(
        "ix_working_file_create_request_task_id",
        table_name="working_file_create_request",
    )
    op.drop_table("working_file_create_request")
