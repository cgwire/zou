"""Index the foreign keys walked by the deletion service

Revision ID: b7d419c25e08
Revises: 4159fed814b5
Create Date: 2026-08-05

Postgres indexes primary keys and unique constraints, never foreign keys.
These three are filtered on by deletion_service, so each cleanup was a full
scan of the child table:

- preview_file.source_file_id, on every output file deletion
- search_filter_group.project_id, on every project deletion
- search_filter_group.person_id, on every person deletion

preview_file is large, so its index is built CONCURRENTLY to keep writes
going. That forbids a surrounding transaction, hence the autocommit block.
A concurrent build can fail and leave the index INVALID; re-running the
migration is safe since the drop below tolerates a missing index.

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d419c25e08"
down_revision = "4159fed814b5"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_preview_file_source_file_id",
            "preview_file",
            ["source_file_id"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )

    # search_filter_group holds per-user saved filters and stays small, so a
    # plain build is short enough not to be worth the concurrent dance.
    op.create_index(
        "ix_search_filter_group_project_id",
        "search_filter_group",
        ["project_id"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_search_filter_group_person_id",
        "search_filter_group",
        ["person_id"],
        unique=False,
        if_not_exists=True,
    )


def downgrade():
    op.drop_index(
        "ix_search_filter_group_person_id",
        table_name="search_filter_group",
        if_exists=True,
    )
    op.drop_index(
        "ix_search_filter_group_project_id",
        table_name="search_filter_group",
        if_exists=True,
    )
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_preview_file_source_file_id",
            table_name="preview_file",
            postgresql_concurrently=True,
            if_exists=True,
        )
