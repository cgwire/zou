"""add color, milestone_type and department_id to milestone

Producers classify milestones (kickoff, review, approval, delivery), so the
schedule can show them as colored labels, and tie them to a department.
Existing rows get the "other" type and no department.

Revision ID: e5b8d1f4a920
Revises: d4f1a7c3e8b2
Create Date: 2026-10-20 10:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

from zou.app.models.milestone import MILESTONE_TYPES

# revision identifiers, used by Alembic.
revision = "e5b8d1f4a920"
down_revision = "d4f1a7c3e8b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("milestone", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("color", sa.String(length=7), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "milestone_type",
                sqlalchemy_utils.types.choice.ChoiceType(MILESTONE_TYPES),
                nullable=False,
                server_default="other",
            )
        )
        batch_op.add_column(
            sa.Column(
                "department_id",
                sqlalchemy_utils.types.uuid.UUIDType(binary=False),
                nullable=True,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_milestone_department_id"),
            ["department_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_milestone_department_id",
            "department",
            ["department_id"],
            ["id"],
        )


def downgrade():
    with op.batch_alter_table("milestone", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_milestone_department_id", type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_milestone_department_id"))
        batch_op.drop_column("department_id")
        batch_op.drop_column("milestone_type")
        batch_op.drop_column("color")
