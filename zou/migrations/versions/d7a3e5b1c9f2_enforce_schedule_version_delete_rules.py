"""enforce the delete rules of the production schedule version tables

The models declare ON DELETE CASCADE on the keys of the production schedule
version, task link and task link assignee tables, but the squashed
migration created those keys without any rule. A database initialized from
it therefore refuses to delete a version holding task links, or a task or a
person linked to a version, while an older database cascades. This
migration puts every such key on the rule its model declares, whatever name
the key carries on the database.

The two nullable references to a version, the version another one was
copied from and the version applied to a project, now fall back to NULL
when that version is deleted instead of blocking the deletion.

Revision ID: d7a3e5b1c9f2
Revises: e8c8e1e2744a
Create Date: 2026-09-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d7a3e5b1c9f2"
down_revision = "e8c8e1e2744a"
branch_labels = None
depends_on = None

# (table, column, referred table, delete rule)
DELETE_RULES = [
    ("production_schedule_version", "project_id", "project", "CASCADE"),
    (
        "production_schedule_version",
        "production_schedule_from",
        "production_schedule_version",
        "SET NULL",
    ),
    (
        "production_schedule_version_task_link",
        "production_schedule_version_id",
        "production_schedule_version",
        "CASCADE",
    ),
    ("production_schedule_version_task_link", "task_id", "task", "CASCADE"),
    (
        "production_schedule_version_task_link_person_link",
        "production_schedule_version_task_link_id",
        "production_schedule_version_task_link",
        "CASCADE",
    ),
    (
        "production_schedule_version_task_link_person_link",
        "person_id",
        "person",
        "CASCADE",
    ),
    (
        "project",
        "from_schedule_version_id",
        "production_schedule_version",
        "SET NULL",
    ),
]


def _find_foreign_key(table, column, referred_table):
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table):
        if (
            foreign_key["constrained_columns"] == [column]
            and foreign_key["referred_table"] == referred_table
        ):
            return foreign_key
    return None


def _set_delete_rule(table, column, referred_table, rule):
    foreign_key = _find_foreign_key(table, column, referred_table)
    # A missing key is left missing: creating it could fail on rows that
    # never had to satisfy it.
    if foreign_key is None:
        return
    current_rule = (foreign_key.get("options") or {}).get("ondelete")
    if (current_rule or "").upper() == (rule or "").upper():
        return
    op.drop_constraint(foreign_key["name"], table, type_="foreignkey")
    op.create_foreign_key(
        foreign_key["name"],
        table,
        referred_table,
        [column],
        ["id"],
        ondelete=rule,
    )


def upgrade():
    for table, column, referred_table, rule in DELETE_RULES:
        _set_delete_rule(table, column, referred_table, rule)


def downgrade():
    # Only the two SET NULL rules are reverted. The cascades stay: older
    # databases always had them, and the deletion paths rely on them.
    for table, column, referred_table, rule in DELETE_RULES:
        if rule == "SET NULL":
            _set_delete_rule(table, column, referred_table, None)
