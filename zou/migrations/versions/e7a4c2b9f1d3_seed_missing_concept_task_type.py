"""Seed missing Concept task type

The pre-1.0.0 squash migration (a1b2c3d4e5f6) dropped the data injection that
the legacy "introduce concepts" migration (feffd3c5b806) used to perform, and
init-data never created it because of a name-only lookup. As a result, the
Concept task type (for_entity="Concept") was missing on instances deployed
between the squash and the fix.

This migration recreates that task type, but only on instances that are
missing it: it is a no-op wherever a Concept task type already exists.

Revision ID: e7a4c2b9f1d3
Revises: 2b8f88aa610f
Create Date: 2026-05-22 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy_utils import UUIDType
from zou.migrations.utils.base import BaseMixin

# revision identifiers, used by Alembic.
revision = "e7a4c2b9f1d3"
down_revision = "2b8f88aa610f"
branch_labels = None
depends_on = None

base = declarative_base()


class TaskType(base, BaseMixin):
    __tablename__ = "task_type"
    name = sa.Column(sa.String(40), nullable=False)
    short_name = sa.Column(sa.String(20))
    color = sa.Column(sa.String(7), default="#FFFFFF")
    priority = sa.Column(sa.Integer, default=1)
    for_entity = sa.Column(sa.String(30), default="Asset")
    allow_timelog = sa.Column(sa.Boolean, default=True)
    archived = sa.Column(sa.Boolean(), default=False)
    shotgun_id = sa.Column(sa.Integer, index=True)
    department_id = sa.Column(
        UUIDType(binary=False), sa.ForeignKey("department.id"), index=True
    )


class Department(base, BaseMixin):
    __tablename__ = "department"
    name = sa.Column(sa.String(80), unique=True, nullable=False)
    color = sa.Column(sa.String(7), nullable=False)
    archived = sa.Column(sa.Boolean(), default=False)


def upgrade():
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # No-op on instances that already have the Concept task type (those that
    # ran the legacy migration). It is hidden in Kitsu and cannot be renamed,
    # so matching on name + for_entity is reliable.
    already_present = (
        session.query(TaskType)
        .filter_by(name="Concept", for_entity="Concept")
        .first()
    )
    if already_present is not None:
        return

    concept_department = (
        session.query(Department).filter_by(name="Concept").one_or_none()
    )
    session.add(
        TaskType(
            name="Concept",
            short_name="",
            color="#8D6E63",
            priority=1,
            for_entity="Concept",
            department_id=(
                concept_department.id
                if concept_department is not None
                else None
            ),
        )
    )
    session.commit()


def downgrade():
    # No-op: we cannot tell whether the Concept task type pre-existed this
    # migration, so we never delete it on downgrade.
    pass
