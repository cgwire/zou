"""Add the trigger conditions and the target guard of status automations

An automation was triggered by one task type set to one status. The trigger
becomes a group stored in in_conditions: an operator (and, or) and
conditions, each a task type with the statuses that meet it. Every existing
row is backfilled with its single condition. The rows that emulate an OR
with one row per input are not merged: their production links and their
revision import flags differ.

out_only_if_task_status_ids lists the statuses the target task has to be in
for a status change to apply; empty or null means no guard.

The downgrade copies the first condition and its first status back into
in_task_type_id and in_task_status_id, and archives the rows it reduces
(several conditions, several statuses or a guard): reduced, they would fire
more widely than they did. An id that names no task type or status, which
only a direct write can store, is copied as null.

Revision ID: e74cbce89021
Revises: a4d8c1f6b3e7
Create Date: 2026-10-16 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e74cbce89021"
down_revision = "a4d8c1f6b3e7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "status_automation",
        sa.Column("in_conditions", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "status_automation",
        sa.Column(
            "out_only_if_task_status_ids", postgresql.JSONB(), nullable=True
        ),
    )
    op.execute("""
        UPDATE status_automation
        SET in_conditions = jsonb_build_object(
            'operator', 'and',
            'conditions', jsonb_build_array(jsonb_build_object(
                'task_type_id', in_task_type_id::text,
                'task_status_ids', jsonb_build_array(in_task_status_id::text)
            ))
        )
        WHERE in_task_type_id IS NOT NULL AND in_task_status_id IS NOT NULL
        """)


def downgrade():
    # The CASE expressions keep jsonb_array_length away from the values
    # that are not arrays (SQL NULL, JSON null): PostgreSQL does not promise
    # to evaluate a WHERE clause from left to right. The ids are looked up
    # as text, not cast: a value that is not a UUID would fail the cast, and
    # a missing row the foreign key, each failing the whole downgrade.
    op.execute("""
        UPDATE status_automation
        SET in_task_type_id = (
                SELECT id FROM task_type
                WHERE id::text =
                    lower(in_conditions #>> '{conditions,0,task_type_id}')
            ),
            in_task_status_id = (
                SELECT id FROM task_status
                WHERE id::text =
                    lower(in_conditions #>> '{conditions,0,task_status_ids,0}')
            ),
            archived = true
        WHERE
            CASE WHEN jsonb_typeof(in_conditions -> 'conditions') = 'array'
                THEN jsonb_array_length(in_conditions -> 'conditions')
                ELSE 0 END > 1
            OR CASE WHEN jsonb_typeof(
                    in_conditions #> '{conditions,0,task_status_ids}'
                ) = 'array'
                THEN jsonb_array_length(
                    in_conditions #> '{conditions,0,task_status_ids}'
                )
                ELSE 0 END > 1
            OR CASE WHEN jsonb_typeof(out_only_if_task_status_ids) = 'array'
                THEN jsonb_array_length(out_only_if_task_status_ids)
                ELSE 0 END > 0
        """)
    op.drop_column("status_automation", "out_only_if_task_status_ids")
    op.drop_column("status_automation", "in_conditions")
