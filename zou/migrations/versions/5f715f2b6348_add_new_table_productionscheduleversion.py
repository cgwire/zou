"""Add new table ProductionScheduleVersion

Revision ID: 5f715f2b6348
Revises: dde6be40f54f
Create Date: 2025-07-11 03:57:29.859765

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "5f715f2b6348"
down_revision = "dde6be40f54f"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "production_schedule_version",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "project_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "production_schedule_from",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=True,
        ),
        sa.Column("locked", sa.Boolean(), nullable=True),
        sa.Column("canceled", sa.Boolean(), nullable=True),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["production_schedule_from"],
            ["production_schedule_version.id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table(
        "production_schedule_version", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_production_schedule_version_production_schedule_from"
            ),
            ["production_schedule_from"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_production_schedule_version_project_id"),
            ["project_id"],
            unique=False,
        )

    op.create_table(
        "production_schedule_version_task_link",
        sa.Column(
            "production_schedule_version_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("start_date", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["production_schedule_version_id"],
            ["production_schedule_version.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["task.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("production_schedule_version_task_link")
    with op.batch_alter_table(
        "production_schedule_version", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_production_schedule_version_project_id")
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_production_schedule_version_production_schedule_from"
            )
        )

    op.drop_table("production_schedule_version")
    # ### end Alembic commands ###
