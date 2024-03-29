"""Person: partial index for email only when not is_bot

Revision ID: 96f58a4a2a58
Revises: b8ed0fb263f8
Create Date: 2024-02-12 03:24:43.601328

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "96f58a4a2a58"
down_revision = "b8ed0fb263f8"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_constraint("person_email_key", type_="unique")
        batch_op.create_index(
            "only_one_email_by_person",
            ["email", "is_bot"],
            unique=True,
            postgresql_where=sa.text("is_bot IS NOT true"),
        )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_index(
            "only_one_email_by_person",
            postgresql_where=sa.text("is_bot IS NOT true"),
        )
        batch_op.create_unique_constraint("person_email_key", ["email"])

    # ### end Alembic commands ###
