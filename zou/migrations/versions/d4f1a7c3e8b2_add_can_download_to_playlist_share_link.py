"""add can_download to playlist share link

Revision ID: d4f1a7c3e8b2
Revises: c7d2e9f4a1b3
Create Date: 2026-11-03 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f1a7c3e8b2"
down_revision = "c7d2e9f4a1b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("playlist_share_link", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "can_download",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade():
    with op.batch_alter_table("playlist_share_link", schema=None) as batch_op:
        batch_op.drop_column("can_download")
