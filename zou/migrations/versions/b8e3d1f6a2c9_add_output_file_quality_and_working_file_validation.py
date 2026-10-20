"""add the quality of the output files and the validation of the working files

Revision ID: b8e3d1f6a2c9
Revises: f3b8d1a6c4e2
Create Date: 2026-10-19 16:00:00.000000

"""

import sqlalchemy as sa
import sqlalchemy_utils
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e3d1f6a2c9"
down_revision = "f3b8d1a6c4e2"
branch_labels = None
depends_on = None

QUALITIES = [
    ("low", "Low"),
    ("mid", "Mid"),
    ("high", "High"),
]

VALIDATION_STATUSES = [
    ("validated", "Validated"),
    ("rejected", "Rejected"),
    ("neutral", "Neutral"),
]


def upgrade():
    with op.batch_alter_table("output_file", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "quality",
                sqlalchemy_utils.types.choice.ChoiceType(QUALITIES),
                nullable=True,
            )
        )
    with op.batch_alter_table("working_file", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "validation_status",
                sqlalchemy_utils.types.choice.ChoiceType(VALIDATION_STATUSES),
                nullable=False,
                server_default="neutral",
            )
        )


def downgrade():
    with op.batch_alter_table("working_file", schema=None) as batch_op:
        batch_op.drop_column("validation_status")
    with op.batch_alter_table("output_file", schema=None) as batch_op:
        batch_op.drop_column("quality")
