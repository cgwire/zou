"""add playlist sharing support

Revision ID: a1bc96e68661
Revises: c4e7f9a3b8d2
Create Date: 2026-04-21 11:28:32.322788

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import uuid

# revision identifiers, used by Alembic.
revision = 'a1bc96e68661'
down_revision = 'c4e7f9a3b8d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('playlist_share_link',
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('playlist_id', sqlalchemy_utils.types.uuid.UUIDType(binary=False), default=uuid.uuid4, nullable=False),
    sa.Column('created_by', sqlalchemy_utils.types.uuid.UUIDType(binary=False), default=uuid.uuid4, nullable=False),
    sa.Column('expiration_date', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('can_comment', sa.Boolean(), nullable=False),
    sa.Column('password', sa.String(length=255), nullable=True),
    sa.Column('id', sqlalchemy_utils.types.uuid.UUIDType(binary=False), default=uuid.uuid4, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['person.id'], ),
    sa.ForeignKeyConstraint(['playlist_id'], ['playlist.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('playlist_share_link', schema=None) as batch_op:
        batch_op.create_index('ix_playlist_share_link_playlist_active', ['playlist_id', 'is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_playlist_share_link_playlist_id'), ['playlist_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_playlist_share_link_token'), ['token'], unique=True)

    with op.batch_alter_table('person', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_guest', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('person', schema=None) as batch_op:
        batch_op.drop_column('is_guest')

    with op.batch_alter_table('playlist_share_link', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_playlist_share_link_token'))
        batch_op.drop_index(batch_op.f('ix_playlist_share_link_playlist_id'))
        batch_op.drop_index('ix_playlist_share_link_playlist_active')

    op.drop_table('playlist_share_link')
