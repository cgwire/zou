"""Detect and optionally repair schemas affected by the buggy pre-1.0.0 squash.

The pre-1.0.0 squash migration (revision a1b2c3d4e5f6) was generated from a
live model snapshot and lost several DDL details (TEXT vs VARCHAR, server
defaults, CHECK constraints, ENUM types, indexes, constraint names). Databases
created from a buggy build of that squash have a schema that diverges from
the one legacy databases hold.

This script probes a target database for each known divergence and reports
or repairs them. The repair logic mirrors the reconciliation Alembic
migration (2b8f88aa610f) and is idempotent — safe to re-run.

Usage:
    python scripts/check_squash_schema.py            # detect only
    python scripts/check_squash_schema.py --fix      # detect and repair

Connection settings are read from the same env vars as zou itself
(DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_DATABASE).
"""

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Callable

import psycopg


@dataclass
class Probe:
    name: str
    description: str
    is_drifted: Callable[[psycopg.Connection], bool]
    repair_sql: str


def text_column_drifted(table: str, column: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT data_type FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            row = cur.fetchone()
            return row is not None and row[0] != "text"

    return check


def server_default_missing(table: str, column: str, expected: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_default FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            row = cur.fetchone()
            return row is not None and (
                row[0] is None or expected not in (row[0] or "")
            )

    return check


def server_default_unexpected(table: str, column: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_default FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s AND column_name = %s
                """,
                (table, column),
            )
            row = cur.fetchone()
            return row is not None and row[0] is not None

    return check


def constraint_missing(name: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s", (name,)
            )
            return cur.fetchone() is None

    return check


def index_missing(name: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public' AND indexname = %s
                """,
                (name,),
            )
            return cur.fetchone() is None

    return check


def email_index_not_partial(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = 'only_one_email_by_person'
            """)
        row = cur.fetchone()
        return row is not None and "WHERE" not in row[0]


def enum_missing(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_type WHERE typname = 'import_source_enum'"
        )
        return cur.fetchone() is None


def constraint_renamed_in_fresh(old: str, new: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s", (old,)
            )
            has_old = cur.fetchone() is not None
            cur.execute(
                "SELECT 1 FROM pg_constraint WHERE conname = %s", (new,)
            )
            has_new = cur.fetchone() is not None
            return has_old and not has_new

    return check


def pk_uc_collapsed(table: str) -> Callable:
    def check(conn):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT contype FROM pg_constraint WHERE conname = %s
                """,
                (f"{table}_uc",),
            )
            row = cur.fetchone()
            return row is not None and row[0] == "p"

    return check


def asset_types_present(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'asset_types'
            """)
        return cur.fetchone() is not None


PROBES: list[Probe] = [
    Probe(
        "asset_types orphan table",
        "Legacy table with no PK or modern usage; should be dropped.",
        asset_types_present,
        "DROP TABLE IF EXISTS asset_types CASCADE",
    ),
    Probe(
        "import_source_enum type missing",
        "ENUM ('csv', 'shotgun') used by data_import_error.source.",
        enum_missing,
        """
        CREATE TYPE public.import_source_enum AS ENUM ('csv', 'shotgun');
        ALTER TABLE data_import_error
            ALTER COLUMN source TYPE public.import_source_enum
            USING source::public.import_source_enum;
        """,
    ),
    Probe(
        "only_one_email_by_person not a partial index",
        "Should be UNIQUE (email, is_bot) WHERE (is_bot IS NOT TRUE).",
        email_index_not_partial,
        """
        DROP INDEX only_one_email_by_person;
        CREATE UNIQUE INDEX only_one_email_by_person
            ON person (email, is_bot)
            WHERE (is_bot IS NOT TRUE);
        """,
    ),
]

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
for table, column in TEXT_COLUMNS:
    PROBES.append(
        Probe(
            f"{table}.{column} should be TEXT",
            f"Squash created it as character varying.",
            text_column_drifted(table, column),
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE text",
        )
    )

SERVER_DEFAULTS = [
    ("entity", "is_shared", "false"),
    ("person", "contract_type", "'open-ended'"),
    ("person", "is_bot", "false"),
    ("status_automation", "import_last_revision", "false"),
    ("task", "difficulty", "3"),
]
for table, column, default in SERVER_DEFAULTS:
    PROBES.append(
        Probe(
            f"{table}.{column} default missing",
            f"Should default to {default}.",
            server_default_missing(table, column, default),
            f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {default}",
        )
    )

PROBES.append(
    Probe(
        "task_status.is_wip default unexpected",
        "Squash added DEFAULT false; prod has no default.",
        server_default_unexpected("task_status", "is_wip"),
        "ALTER TABLE task_status ALTER COLUMN is_wip DROP DEFAULT",
    )
)

CHECK_CONSTRAINTS = [
    ("check_difficulty", "task", "((difficulty > 0) AND (difficulty < 6))"),
    ("day_off_date_check", "day_off", "(date <= end_date)"),
    (
        "check_duration_positive",
        "time_spent",
        "(duration > (0)::double precision)",
    ),
]
for cname, table, expr in CHECK_CONSTRAINTS:
    PROBES.append(
        Probe(
            f"CHECK {cname} missing",
            f"Lost in squash on table {table}.",
            constraint_missing(cname),
            f"ALTER TABLE {table} ADD CONSTRAINT {cname} CHECK {expr}",
        )
    )

MISSING_INDEXES = [
    ("ix_entity_entity_type_parent", "entity", "(entity_type_id, parent_id)"),
    (
        "ix_entity_entity_type_project",
        "entity",
        "(entity_type_id, project_id)",
    ),
    ("ix_task_entity_project", "task", "(entity_id, project_id)"),
]
for idx, table, cols in MISSING_INDEXES:
    PROBES.append(
        Probe(
            f"index {idx} missing",
            f"Lost legacy performance index on {table}.",
            index_missing(idx),
            f"CREATE INDEX {idx} ON {table} {cols}",
        )
    )

CONSTRAINT_RENAMES = [
    ("entity_preview_file_id_fkey", "fk_main_preview", "entity"),
    ("entity_ready_for_fkey", "fk_ready_for", "entity"),
    ("task_person_link_pkey", "assignations_pkey", "task_person_link"),
]
for old, new, table in CONSTRAINT_RENAMES:
    PROBES.append(
        Probe(
            f"constraint renamed: {old} should be {new}",
            f"Squash auto-named what legacy had as {new}.",
            constraint_renamed_in_fresh(old, new),
            f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}",
        )
    )

PK_UC_TABLES = [
    ("department_link", "person_id, department_id"),
    (
        "department_metadata_descriptor_link",
        "metadata_descriptor_id, department_id",
    ),
    ("task_type_asset_type_link", "asset_type_id, task_type_id"),
]
for table, cols in PK_UC_TABLES:
    PROBES.append(
        Probe(
            f"{table}: PK and UC collapsed into {table}_uc",
            f"Should have separate {table}_pkey and {table}_uc.",
            pk_uc_collapsed(table),
            f"""
            ALTER TABLE {table} RENAME CONSTRAINT {table}_uc TO {table}_pkey;
            ALTER TABLE {table} ADD CONSTRAINT {table}_uc UNIQUE ({cols});
            """,
        )
    )


def connect() -> psycopg.Connection:
    dsn = (
        f"host={os.environ.get('DB_HOST', 'localhost')} "
        f"port={os.environ.get('DB_PORT', '5432')} "
        f"user={os.environ['DB_USERNAME']} "
        f"password={os.environ['DB_PASSWORD']} "
        f"dbname={os.environ['DB_DATABASE']}"
    )
    return psycopg.connect(dsn)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply repair SQL for every detected drift.",
    )
    args = parser.parse_args()

    drifted = []
    with connect() as conn:
        for probe in PROBES:
            try:
                if probe.is_drifted(conn):
                    drifted.append(probe)
            except psycopg.Error as exc:
                print(f"  warning: probe '{probe.name}' raised {exc!r}")
                conn.rollback()

        if not drifted:
            print("Schema is in sync with the reconciled state.")
            return 0

        print(f"Detected {len(drifted)} drift(s):")
        for p in drifted:
            print(f"  - {p.name}: {p.description}")

        if not args.fix:
            print("\nRun with --fix to repair, or apply via `zou upgrade-db`.")
            return 1

        print("\nApplying repairs...")
        for p in drifted:
            print(f"  → {p.name}")
            with conn.cursor() as cur:
                cur.execute(p.repair_sql)
            conn.commit()
        print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
