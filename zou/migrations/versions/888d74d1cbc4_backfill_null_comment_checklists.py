"""Backfill the null comment checklists

Revision ID: 888d74d1cbc4
Revises: c4e8a1f6d2b9
Create Date: 2026-10-02 15:39:05.000000

"""

from alembic import op

revision = "888d74d1cbc4"
down_revision = "c4e8a1f6d2b9"
branch_labels = None
depends_on = None


def upgrade():
    # Kitsu and the comment update check expect a list. The comments older
    # than the column, or created without a checklist, hold a SQL NULL. The
    # ones a sync or an API call set to None hold the JSON null instead.
    op.execute(
        "UPDATE comment SET checklist = '[]'::jsonb "
        "WHERE checklist IS NULL OR checklist = 'null'::jsonb"
    )


def downgrade():
    # The former nulls cannot be told apart from the empty lists.
    pass
