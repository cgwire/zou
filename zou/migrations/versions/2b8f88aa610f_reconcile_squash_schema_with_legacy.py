"""reconcile squash schema with legacy state

The pre-1.0.0 squash migration was auto-generated from a live model snapshot
and lost several DDL details that the historical chain had set:

- description/text/comment columns rendered as VARCHAR instead of TEXT
- server defaults dropped on several boolean/numeric columns
- CHECK constraints dropped on task.difficulty, day_off date range, time_spent
- import_source_enum ENUM type collapsed to character varying(7)
- 3 composite indexes lost (entity, task perf indexes from legacy
  71d546ace0ee / 0c05b22194f3)
- only_one_email_by_person index lost its WHERE (is_bot IS NOT TRUE) clause
- legacy FK names (fk_main_preview, fk_ready_for) and PK name (assignations_pkey)
  replaced by SQLAlchemy auto-generated ones
- PK+UC pairs on link tables collapsed into a single constraint named *_uc

This migration brings fresh installs back in line with the legacy schema.
Every operation is idempotent: it is no-op on databases that already match
prod and corrective on databases coming from the squash.

Revision ID: 2b8f88aa610f
Revises: 25d2d8dba46f
Create Date: 2026-04-28 00:00:00.000000

"""

from alembic import op

revision = "2b8f88aa610f"
down_revision = "25d2d8dba46f"
branch_labels = None
depends_on = None


# (table, column) pairs whose squash type "character varying" must become TEXT.
TEXT_COLUMNS = [
    ("chat_message", "text"),
    ("comment", "text"),
    ("day_off", "description"),
    ("entity", "description"),
    ("entity_type", "description"),
    ("output_file", "comment"),
    ("output_file", "description"),
    ("plugin", "description"),
    ("preview_file", "description"),
    ("project", "description"),
    ("task", "description"),
    ("task_status", "description"),
    ("task_type", "description"),
    ("working_file", "comment"),
    ("working_file", "description"),
]

# (table, column, default_sql) — set/restore server defaults.
SERVER_DEFAULTS = [
    ("entity", "is_shared", "false"),
    ("person", "contract_type", "'open-ended'::character varying"),
    ("person", "is_bot", "false"),
    ("status_automation", "import_last_revision", "false"),
    ("task", "difficulty", "3"),
]

# Defaults the squash added that prod does not have.
DEFAULTS_TO_DROP = [
    ("task_status", "is_wip"),
]

# (constraint_name, table, definition) — CHECK constraints lost in squash.
CHECK_CONSTRAINTS = [
    (
        "check_difficulty",
        "task",
        "(((difficulty > 0) AND (difficulty < 6)))",
    ),
    (
        "day_off_date_check",
        "day_off",
        "((date <= end_date))",
    ),
    (
        "check_duration_positive",
        "time_spent",
        "((duration > (0)::double precision))",
    ),
]

# Indexes that legacy had but the squash dropped.
MISSING_INDEXES = [
    (
        "ix_entity_entity_type_parent",
        "entity",
        "(entity_type_id, parent_id)",
    ),
    (
        "ix_entity_entity_type_project",
        "entity",
        "(entity_type_id, project_id)",
    ),
    (
        "ix_task_entity_project",
        "task",
        "(entity_id, project_id)",
    ),
]

# (old_name, new_name, table) — constraint renames that fresh DBs need.
# Conditional on old_name existing → no-op on legacy DBs.
CONSTRAINT_RENAMES = [
    ("entity_preview_file_id_fkey", "fk_main_preview", "entity"),
    ("entity_ready_for_fkey", "fk_ready_for", "entity"),
    ("task_person_link_pkey", "assignations_pkey", "task_person_link"),
]

# Tables where fresh DBs collapsed PK and UC into a single constraint named
# *_uc. We need to rename it to *_pkey and re-add a UC alongside.
PK_UC_SPLIT = [
    ("department_link", "person_id, department_id"),
    (
        "department_metadata_descriptor_link",
        "metadata_descriptor_id, department_id",
    ),
    ("task_type_asset_type_link", "asset_type_id, task_type_id"),
]


def upgrade():
    # 1. Ensure import_source_enum exists, then convert the column.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type WHERE typname = 'import_source_enum'
            ) THEN
                CREATE TYPE public.import_source_enum AS ENUM ('csv', 'shotgun');
            END IF;
        END
        $$;
        """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'data_import_error'
                  AND column_name = 'source'
                  AND data_type = 'character varying'
            ) THEN
                ALTER TABLE data_import_error
                    ALTER COLUMN source TYPE public.import_source_enum
                    USING source::public.import_source_enum;
            END IF;
        END
        $$;
        """)

    # 2. Restore TEXT column types.
    for table, column in TEXT_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE text")

    # 3. Restore server defaults.
    for table, column, default_sql in SERVER_DEFAULTS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"SET DEFAULT {default_sql}"
        )

    # 4. Drop unwanted defaults that the squash added.
    for table, column in DEFAULTS_TO_DROP:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")

    # 5. Add missing CHECK constraints (idempotent via pg_constraint check).
    for cname, table, expr in CHECK_CONSTRAINTS:
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{cname}'
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT {cname} CHECK {expr};
                END IF;
            END
            $$;
            """)

    # 6. Add missing indexes.
    for idx_name, table, columns in MISSING_INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} {columns}"
        )

    # 7. Replace only_one_email_by_person with its partial version.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND indexname = 'only_one_email_by_person'
                  AND indexdef NOT LIKE '%WHERE%'
            ) THEN
                DROP INDEX only_one_email_by_person;
                CREATE UNIQUE INDEX only_one_email_by_person
                    ON person (email, is_bot)
                    WHERE (is_bot IS NOT TRUE);
            END IF;
        END
        $$;
        """)

    # 8. Rename constraints that fresh DBs got with auto-generated names.
    for old, new, table in CONSTRAINT_RENAMES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{old}'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{new}'
                ) THEN
                    ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new};
                END IF;
            END
            $$;
            """)

    # 9. Split collapsed PK+UC constraints on link tables.
    # On fresh DBs, the constraint named <table>_uc is actually the PK; in
    # prod, <table>_pkey is the PK and <table>_uc is a separate UNIQUE.
    for table, cols in PK_UC_SPLIT:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{table}_uc' AND contype = 'p'
                ) AND NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{table}_pkey'
                ) THEN
                    ALTER TABLE {table}
                        RENAME CONSTRAINT {table}_uc TO {table}_pkey;
                    ALTER TABLE {table}
                        ADD CONSTRAINT {table}_uc UNIQUE ({cols});
                END IF;
            END
            $$;
            """)


def downgrade():
    pass
