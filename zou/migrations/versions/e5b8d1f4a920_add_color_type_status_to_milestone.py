"""add color, milestone_type and status to milestone

Producers classify milestones (kickoff, review, approval, delivery) and
track whether they are reached, so the schedule can show them as colored
labels. Existing rows get the "other" type and the "todo" status.

Revision ID: e5b8d1f4a920
Revises: b8e3d1f6a2c9
Create Date: 2026-10-20 10:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

from zou.app.models.milestone import MILESTONE_STATUSES, MILESTONE_TYPES

# revision identifiers, used by Alembic.
revision = "e5b8d1f4a920"
down_revision = "b8e3d1f6a2c9"
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
                "status",
                sqlalchemy_utils.types.choice.ChoiceType(MILESTONE_STATUSES),
                nullable=False,
                server_default="todo",
            )
        )


def downgrade():
    with op.batch_alter_table("milestone", schema=None) as batch_op:
        batch_op.drop_column("status")
        batch_op.drop_column("milestone_type")
        batch_op.drop_column("color")
