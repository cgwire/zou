"""Add the SAML identity to persons

Revision ID: a91c4e7d2f65
Revises: 7b3d9e5a1c42
Create Date: 2026-10-05 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "a91c4e7d2f65"
down_revision = "7b3d9e5a1c42"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.add_column(sa.Column("saml_issuer", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("saml_subject", sa.String(length=255), nullable=True)
        )
        batch_op.create_unique_constraint(
            "person_saml_identity_uc", ["saml_issuer", "saml_subject"]
        )


def downgrade():
    with op.batch_alter_table("person", schema=None) as batch_op:
        batch_op.drop_constraint("person_saml_identity_uc", type_="unique")
        batch_op.drop_column("saml_subject")
        batch_op.drop_column("saml_issuer")
