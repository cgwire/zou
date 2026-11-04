"""add project_template_asset_type_task_type_link

A project template can carry the production workflows of its asset types.

Revision ID: a4d8c1f6b3e7
Revises: f3c7b9e2a1d4
Create Date: 2026-11-03 18:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4d8c1f6b3e7"
down_revision = "f3c7b9e2a1d4"
branch_labels = None
depends_on = None

TABLE = "project_template_asset_type_task_type_link"
COLUMNS = ["project_template_id", "asset_type_id", "task_type_id"]


def upgrade():
    uuid_type = sqlalchemy_utils.types.uuid.UUIDType(binary=False)
    op.create_table(
        TABLE,
        sa.Column("project_template_id", uuid_type, nullable=False),
        sa.Column("asset_type_id", uuid_type, nullable=False),
        sa.Column("task_type_id", uuid_type, nullable=False),
        sa.ForeignKeyConstraint(
            ["project_template_id"], ["project_template.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["asset_type_id"], ["entity_type.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["task_type_id"], ["task_type.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint(*COLUMNS),
    )
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        for column in COLUMNS:
            batch_op.create_index(
                batch_op.f(f"ix_{TABLE}_{column}"), [column], unique=False
            )


def downgrade():
    op.drop_table(TABLE)
