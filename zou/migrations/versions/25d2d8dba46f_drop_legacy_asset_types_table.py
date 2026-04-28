"""drop legacy asset_types table

The asset_types table is a pre-Alembic relic: a 2-column M2M without a primary
key, holding the same shape as the modern task_type_asset_type_link table that
fully replaced it. No application code references it. It survives only on
databases that existed before Alembic tracking. Drop it where it still exists.

Revision ID: 25d2d8dba46f
Revises: a1bc96e68661
Create Date: 2026-04-28 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "25d2d8dba46f"
down_revision = "a1bc96e68661"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS asset_types CASCADE")


def downgrade():
    pass
