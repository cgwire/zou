"""Empty revision due to wrong revision creation

Revision ID: 5ab9d7a75887
Revises: d80267806131
Create Date: 2022-06-06 22:33:26.331874

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = "5ab9d7a75887"
down_revision = "d80267806131"
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
