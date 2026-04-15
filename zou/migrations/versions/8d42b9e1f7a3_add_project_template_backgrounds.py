"""add project template preview background support

Revision ID: 8d42b9e1f7a3
Revises: 7c91a4b3d2e0
Create Date: 2026-04-14 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "8d42b9e1f7a3"
down_revision = "7c91a4b3d2e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_template_preview_background_file_link",
        sa.Column(
            "project_template_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.Column(
            "preview_background_file_id",
            sqlalchemy_utils.types.uuid.UUIDType(binary=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_template_id"], ["project_template.id"]
        ),
        sa.ForeignKeyConstraint(
            ["preview_background_file_id"], ["preview_background_file.id"]
        ),
        sa.PrimaryKeyConstraint(
            "project_template_id", "preview_background_file_id"
        ),
    )
    with op.batch_alter_table(
        "project_template_preview_background_file_link", schema=None
    ) as batch_op:
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_preview_background_file_link_project_template_id"
            ),
            ["project_template_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_preview_background_file_link_preview_background_file_id"
            ),
            ["preview_background_file_id"],
            unique=False,
        )

    with op.batch_alter_table("project_template", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "default_preview_background_file_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f(
                "ix_project_template_default_preview_background_file_id"
            ),
            ["default_preview_background_file_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "project_template_default_preview_background_file_id_fkey",
            "preview_background_file",
            ["default_preview_background_file_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("project_template", schema=None) as batch_op:
        batch_op.drop_constraint(
            "project_template_default_preview_background_file_id_fkey",
            type_="foreignkey",
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_default_preview_background_file_id"
            )
        )
        batch_op.drop_column("default_preview_background_file_id")

    with op.batch_alter_table(
        "project_template_preview_background_file_link", schema=None
    ) as batch_op:
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_preview_background_file_link_preview_background_file_id"
            )
        )
        batch_op.drop_index(
            batch_op.f(
                "ix_project_template_preview_background_file_link_project_template_id"
            )
        )
    op.drop_table("project_template_preview_background_file_link")
