"""merge the two migration heads

The foreign key index migration e1a7c3d9b5f2 was written on c4e8a2f1d6b3,
while c4e8a1f6d2b9, then 888d74d1cbc4 on top of it, landed on that same
parent: the migrations had two heads, and upgrade-db stopped on
MultipleHeads before upgrading anything.

A merge leaves both branches as they are, so a database runs whichever
one it misses. Chaining the index migration after 888d74d1cbc4 instead
would make a database that already ran it skip the two others.

Revision ID: e8c8e1e2744a
Revises: 888d74d1cbc4, e1a7c3d9b5f2
Create Date: 2026-10-05 17:30:00.000000

"""

revision = "e8c8e1e2744a"
down_revision = ("888d74d1cbc4", "e1a7c3d9b5f2")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
