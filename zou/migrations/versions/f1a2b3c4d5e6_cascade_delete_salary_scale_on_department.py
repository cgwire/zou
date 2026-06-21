"""cascade delete salary scale entries when a department is deleted

Salary scale rows are auto-generated for every department/position/seniority
combination and have no meaning without their department, so they should be
removed together with it. The foreign key is recreated with ON DELETE CASCADE
to replace the default RESTRICT behaviour that blocked department deletion.

Revision ID: f1a2b3c4d5e6
Revises: c5e8b2a4f1d3
Create Date: 2026-06-21 10:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "c5e8b2a4f1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint(
        "salary_scale_department_id_fkey",
        "salary_scale",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "salary_scale_department_id_fkey",
        "salary_scale",
        "department",
        ["department_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "salary_scale_department_id_fkey",
        "salary_scale",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "salary_scale_department_id_fkey",
        "salary_scale",
        "department",
        ["department_id"],
        ["id"],
    )
