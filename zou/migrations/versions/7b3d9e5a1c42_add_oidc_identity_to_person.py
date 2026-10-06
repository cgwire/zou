"""Add the OIDC identity to persons

Revision ID: 7b3d9e5a1c42
Revises: d7a3e5b1c9f2
Create Date: 2026-10-05 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "7b3d9e5a1c42"
down_revision = "d7a3e5b1c9f2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(sa.Column("oidc_issuer", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("oidc_subject", sa.String(length=255), nullable=True)
        )
        batch_op.create_unique_constraint(
            "person_oidc_identity_uc", ["oidc_issuer", "oidc_subject"]
        )


def downgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_constraint("person_oidc_identity_uc", type_="unique")
        batch_op.drop_column("oidc_subject")
        batch_op.drop_column("oidc_issuer")
