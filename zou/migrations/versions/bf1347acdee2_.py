"""empty message

Revision ID: bf1347acdee2
Revises: b4dd0add5f79
Create Date: 2018-03-23 17:08:11.289953

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "bf1347acdee2"
down_revision = "b4dd0add5f79"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column(
        "task_type",
        sa.Column("for_entity", sa.String(length=10), nullable=True),
    )
    op.drop_constraint("task_type_uc", "task_type", type_="unique")
    op.create_unique_constraint(
        "task_type_uc", "task_type", ["name", "for_entity", "department_id"]
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint("task_type_uc", "task_type", type_="unique")
    op.create_unique_constraint(
        "task_type_uc", "task_type", ["name", "department_id"]
    )
    op.drop_column("task_type", "for_entity")
    # ### end Alembic commands ###
