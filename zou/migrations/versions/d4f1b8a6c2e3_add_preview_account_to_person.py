"""add preview account columns to person

Revision ID: d4f1b8a6c2e3
Revises: c3e9a7d1f5b2
Create Date: 2026-10-18 00:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

revision = "d4f1b8a6c2e3"
down_revision = "c3e9a7d1f5b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "preview_project_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("preview_opened_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("preview_open_until", sa.DateTime(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_person_preview_project_id"),
            ["preview_project_id"],
            unique=True,
        )
        batch_op.create_foreign_key(
            "person_preview_project_id_fkey",
            "project",
            ["preview_project_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_constraint(
            "person_preview_project_id_fkey", type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_person_preview_project_id"))
        batch_op.drop_column("preview_open_until")
        batch_op.drop_column("preview_opened_at")
        batch_op.drop_column("preview_project_id")
