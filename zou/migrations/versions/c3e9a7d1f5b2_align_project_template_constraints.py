"""align project template constraints with the models

The project template migration declared name unique twice (a constraint and
a unique index), and a unique constraint on the same columns as the primary
key of two link tables, which PostgreSQL folded into the key. Autogenerate
reported both against the models on every run.

- drop project_template_name_key, ix_project_template_name stays
- split the primary key and the unique constraint of the two link tables,
  as 2b8f88aa610f did for the other link tables

Every operation is idempotent.

Revision ID: c3e9a7d1f5b2
Revises: b5d2e8f3a1c7
Create Date: 2026-10-12 00:00:00.000000

"""

from alembic import op

revision = "c3e9a7d1f5b2"
down_revision = "b5d2e8f3a1c7"
branch_labels = None
depends_on = None

# (table, unique constraint name, columns)
LINK_TABLES = [
    (
        "project_template_task_type_link",
        "project_template_tasktype_uc",
        "project_template_id, task_type_id",
    ),
    (
        "project_template_task_status_link",
        "project_template_taskstatus_uc",
        "project_template_id, task_status_id",
    ),
]


def upgrade():
    op.execute(
        "ALTER TABLE project_template "
        "DROP CONSTRAINT IF EXISTS project_template_name_key"
    )
    for table, uc_name, columns in LINK_TABLES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{uc_name}' AND contype = 'p'
                      AND conrelid = '{table}'::regclass
                ) THEN
                    ALTER TABLE {table}
                        RENAME CONSTRAINT {uc_name} TO {table}_pkey;
                    ALTER TABLE {table}
                        ADD CONSTRAINT {uc_name} UNIQUE ({columns});
                END IF;
            END
            $$;
            """)


def downgrade():
    for table, uc_name, _ in LINK_TABLES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{table}_pkey' AND contype = 'p'
                      AND conrelid = '{table}'::regclass
                ) THEN
                    ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {uc_name};
                    ALTER TABLE {table}
                        RENAME CONSTRAINT {table}_pkey TO {uc_name};
                END IF;
            END
            $$;
            """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'project_template_name_key'
                  AND conrelid = 'project_template'::regclass
            ) THEN
                ALTER TABLE project_template
                    ADD CONSTRAINT project_template_name_key UNIQUE (name);
            END IF;
        END
        $$;
        """)
