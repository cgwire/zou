"""Add role to project person link

Revision ID: 4159fed814b5
Revises: f3a7c1e9b5d2
Create Date: 2026-07-22

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils

from zou.app.models.person import ROLE_TYPES

# revision identifiers, used by Alembic.
revision = "4159fed814b5"
down_revision = "f3a7c1e9b5d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project_person_link", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                sqlalchemy_utils.types.choice.ChoiceType(ROLE_TYPES),
                nullable=True,
            )
        )


def downgrade():
    with op.batch_alter_table("project_person_link", schema=None) as batch_op:
        batch_op.drop_column("role")
