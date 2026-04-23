"""For ProjectTaskStatusLink set default roles_for_board

Revision ID: deeacd38d373
Revises: 20dfeb36142b
Create Date: 2024-01-16 23:48:25.874470

"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.orm.session import Session
from sqlalchemy.ext.declarative import declarative_base
from zou.migrations.utils.base import BaseMixin

# revision identifiers, used by Alembic.
revision = "deeacd38d373"
down_revision = "20dfeb36142b"
branch_labels = None
depends_on = None

base = declarative_base()

ROLE_TYPES = [
    ("user", "Artist"),
    ("admin", "Studio Manager"),
    ("supervisor", "Supervisor"),
    ("manager", "Production Manager"),
    ("client", "Client"),
    ("vendor", "Vendor"),
]


class ProjectTaskStatusLink(base, BaseMixin):
    __tablename__ = "project_task_status_link"
    project_id = sa.Column(
        sqlalchemy_utils.types.UUIDType(binary=False),
        primary_key=True,
    )
    task_status_id = sa.Column(
        sqlalchemy_utils.types.UUIDType(binary=False),
        primary_key=True,
    )
    priority = sa.Column(sa.Integer, default=None)
    roles_for_board = sa.Column(
        sa.ARRAY(sqlalchemy_utils.types.choice.ChoiceType(ROLE_TYPES)),
        default=["user", "admin", "supervisor", "manager", "vendor"],
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "task_status_id", name="project_taskstatus_uc"
        ),
    )


def upgrade():
    session = Session(bind=op.get_bind())
    session.query(ProjectTaskStatusLink).update(
        {
            ProjectTaskStatusLink.roles_for_board: [
                "user",
                "admin",
                "supervisor",
                "manager",
                "vendor",
            ]
        }
    )
    session.commit()


def downgrade():
    pass
