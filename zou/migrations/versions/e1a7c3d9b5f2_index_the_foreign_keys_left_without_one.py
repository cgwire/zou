"""index the foreign keys left without one

Nine foreign key columns had no index: PostgreSQL scanned the whole
table on every deletion of the row they reference (a person, a preview
file, a filter group), and on the joins that read them. comment and
preview_file are the largest tables of an instance.

Revision ID: e1a7c3d9b5f2
Revises: c4e8a2f1d6b3
Create Date: 2026-09-27 10:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e1a7c3d9b5f2"
down_revision = "c4e8a2f1d6b3"
branch_labels = None
depends_on = None

INDEXES = [
    ("asset_instance", "entity_id"),
    ("asset_instance", "entity_type_id"),
    ("comment", "preview_file_id"),
    ("entity", "created_by"),
    ("playlist", "created_by"),
    ("playlist_share_link", "created_by"),
    ("preview_file", "person_id"),
    ("search_filter", "department_id"),
    ("search_filter", "search_filter_group_id"),
    ("search_filter_group", "department_id"),
]


def upgrade():
    for table, column in INDEXES:
        op.create_index(
            op.f(f"ix_{table}_{column}"), table, [column], unique=False
        )


def downgrade():
    for table, column in reversed(INDEXES):
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
