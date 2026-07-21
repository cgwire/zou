"""Add task_type_id to metadata_descriptor for task metadata

Revision ID: f3a7c1e9b5d2
Revises: e8b2c4d6f1a3
Create Date: 2026-07-20 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils

revision = "f3a7c1e9b5d2"
down_revision = "e8b2c4d6f1a3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("metadata_descriptor", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "task_type_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_metadata_descriptor_task_type_id"),
            ["task_type_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_metadata_descriptor_task_type_id",
            "task_type",
            ["task_type_id"],
            ["id"],
        )
        # The plain unique constraints become partial unique indexes:
        # NULLs are distinct in Postgres unique constraints, so a single
        # constraint including task_type_id would stop protecting
        # non-Task descriptors from duplicates.
        batch_op.drop_constraint("metadata_descriptor_uc", type_="unique")
        batch_op.drop_constraint("metadata_descriptor_uc2", type_="unique")
    op.create_index(
        "metadata_descriptor_uc",
        "metadata_descriptor",
        ["project_id", "entity_type", "name"],
        unique=True,
        postgresql_where=sa.text("task_type_id IS NULL"),
    )
    op.create_index(
        "metadata_descriptor_uc2",
        "metadata_descriptor",
        ["project_id", "entity_type", "field_name"],
        unique=True,
        postgresql_where=sa.text("task_type_id IS NULL"),
    )
    op.create_index(
        "metadata_descriptor_task_type_uc",
        "metadata_descriptor",
        ["project_id", "entity_type", "task_type_id", "name"],
        unique=True,
        postgresql_where=sa.text("task_type_id IS NOT NULL"),
    )
    op.create_index(
        "metadata_descriptor_task_type_uc2",
        "metadata_descriptor",
        ["project_id", "entity_type", "task_type_id", "field_name"],
        unique=True,
        postgresql_where=sa.text("task_type_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("metadata_descriptor_task_type_uc2", "metadata_descriptor")
    op.drop_index("metadata_descriptor_task_type_uc", "metadata_descriptor")
    op.drop_index("metadata_descriptor_uc2", "metadata_descriptor")
    op.drop_index("metadata_descriptor_uc", "metadata_descriptor")
    with op.batch_alter_table("metadata_descriptor", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_metadata_descriptor_task_type_id", type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_metadata_descriptor_task_type_id"))
        batch_op.drop_column("task_type_id")
        batch_op.create_unique_constraint(
            "metadata_descriptor_uc", ["project_id", "entity_type", "name"]
        )
        batch_op.create_unique_constraint(
            "metadata_descriptor_uc2",
            ["project_id", "entity_type", "field_name"],
        )
