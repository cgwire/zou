"""add a message column to build job

The playlist builder can fall back from the exact concat demuxer to the
re-encoding concat filter, whose output timing can drift. The message
column lets the build report such a degraded run instead of a plain
success.

Revision ID: a3f7c2d91b45
Revises: b7d419c25e08
Create Date: 2026-08-24 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f7c2d91b45"
down_revision = "b7d419c25e08"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("build_job", sa.Column("message", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("build_job", "message")
