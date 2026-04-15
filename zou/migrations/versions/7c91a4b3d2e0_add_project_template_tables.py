"""add project template tables

Revision ID: 7c91a4b3d2e0
Revises: 68bae7fcd569
Create Date: 2026-04-08 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import uuid

from zou.app.models.person import ROLE_TYPES
from zou.app.models.project import PROJECT_STYLES


# revision identifiers, used by Alembic.
revision = "7c91a4b3d2e0"
down_revision = "68bae7fcd569"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_template",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fps", sa.String(length=10), nullable=True),
        sa.Column("ratio", sa.String(length=10), nullable=True),
        sa.Column("resolution", sa.String(length=12), nullable=True),
        sa.Column("production_type", sa.String(length=20), nullable=True),
        sa.Column(
            "production_style",
            sqlalchemy_utils.types.choice.ChoiceType(PROJECT_STYLES),
            nullable=False,
        ),
        sa.Column("max_retakes", sa.Integer(), nullable=True),
        sa.Column("is_clients_isolated", sa.Boolean(), nullable=True),
        sa.Column("is_preview_download_allowed", sa.Boolean(), nullable=True),
        sa.Column("is_set_preview_automated", sa.Boolean(), nullable=True),
        sa.Column(
            "is_publish_default_for_artists", sa.Boolean(), nullable=True
        ),
        sa.Column("homepage", sa.String(length=80), nullable=True),
        sa.Column("hd_bitrate_compression", sa.Integer(), nullable=True),
        sa.Column("ld_bitrate_compression", sa.Integer(), nullable=True),
        sa.Column(
            "file_tree",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "data",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "metadata_descriptors",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("project_template", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_template_name"), ["name"], unique=True
        )

    op.create_table(
        "project_template_task_type_link",
        sa.Column(
            "project_template_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "task_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column(
            "id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            default=uuid.uuid4,
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_template_id"], ["project_template.id"]
        ),
        sa.ForeignKeyConstraint(["task_type_id"], ["task_type.id"]),
        sa.PrimaryKeyConstraint("project_template_id", "task_type_id"),
        sa.UniqueConstraint(
            "project_template_id",
            "task_type_id",
            name="project_template_tasktype_uc",
        ),
    )
    with op.batch_alter_table(
        "project_template_task_type_link", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_project_template_task_type_link_project_template_id"),
            ["project_template_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_project_template_task_type_link_task_type_id"),
            ["task_type_id"],
            unique=False,
        )

    op.create_table(
        "project_template_task_status_link",
        sa.Column(
            "project_template_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "task_status_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column(
            "roles_for_board",
            sa.ARRAY(sqlalchemy_utils.types.choice.ChoiceType(ROLE_TYPES)),
            nullable=True,
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
            ["project_template_id"], ["project_template.id"]
        ),
        sa.ForeignKeyConstraint(["task_status_id"], ["task_status.id"]),
        sa.PrimaryKeyConstraint("project_template_id", "task_status_id"),
        sa.UniqueConstraint(
            "project_template_id",
            "task_status_id",
            name="project_template_taskstatus_uc",
        ),
    )
    with op.batch_alter_table(
        "project_template_task_status_link", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_task_status_link_project_template_id"
            ),
            ["project_template_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_project_template_task_status_link_task_status_id"),
            ["task_status_id"],
            unique=False,
        )

    op.create_table(
        "project_template_asset_type_link",
        sa.Column(
            "project_template_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "asset_type_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_template_id"], ["project_template.id"]
        ),
        sa.ForeignKeyConstraint(["asset_type_id"], ["entity_type.id"]),
        sa.PrimaryKeyConstraint("project_template_id", "asset_type_id"),
    )
    with op.batch_alter_table(
        "project_template_asset_type_link", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_asset_type_link_project_template_id"
            ),
            ["project_template_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_project_template_asset_type_link_asset_type_id"),
            ["asset_type_id"],
            unique=False,
        )

    op.create_table(
        "project_template_status_automation_link",
        sa.Column(
            "project_template_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "status_automation_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_template_id"], ["project_template.id"]
        ),
        sa.ForeignKeyConstraint(
            ["status_automation_id"], ["status_automation.id"]
        ),
        sa.PrimaryKeyConstraint(
            "project_template_id", "status_automation_id"
        ),
    )
    with op.batch_alter_table(
        "project_template_status_automation_link", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_status_automation_link_project_template_id"
            ),
            ["project_template_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_status_automation_link_status_automation_id"
            ),
            ["status_automation_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table(
        "project_template_status_automation_link", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_status_automation_link_status_automation_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_status_automation_link_project_template_id"
            )
        )
    op.drop_table("project_template_status_automation_link")

    with op.batch_alter_table(
        "project_template_asset_type_link", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_project_template_asset_type_link_asset_type_id")
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_asset_type_link_project_template_id"
            )
        )
    op.drop_table("project_template_asset_type_link")

    with op.batch_alter_table(
        "project_template_task_status_link", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_project_template_task_status_link_task_status_id")
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_task_status_link_project_template_id"
            )
        )
    op.drop_table("project_template_task_status_link")

    with op.batch_alter_table(
        "project_template_task_type_link", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_project_template_task_type_link_task_type_id")
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_task_type_link_project_template_id"
            )
        )
    op.drop_table("project_template_task_type_link")

    with op.batch_alter_table("project_template", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_project_template_name"))
    op.drop_table("project_template")
