"""sanitize person locales that Python Babel cannot parse

An unparseable locale (e.g. "da_DA" instead of "da_DK") used to be stored
verbatim on the person, then broke every later read since LocaleType re-parses
the column through Babel on load. A single poisoned row takes down login and
the whole persons list. New writes are now rejected upstream, but rows that
were already poisoned must be healed: this migration reads the raw locale
values (bypassing the coercion that raises on those rows) and blanks out any
value Babel cannot parse. NULL is safe here, the read paths fall back to the
default locale.

Revision ID: f2c9a1b7e4d8
Revises: a3d9c1e7b5f2
Create Date: 2026-07-06 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from babel import Locale
from babel.core import UnknownLocaleError


# revision identifiers, used by Alembic.
revision = "f2c9a1b7e4d8"
down_revision = "a3d9c1e7b5f2"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Read raw strings through a textual query so the LocaleType coercion,
    # which raises on the poisoned rows, is never triggered.
    rows = connection.execute(
        sa.text("SELECT id, locale FROM person WHERE locale IS NOT NULL")
    ).fetchall()

    invalid_ids = []
    for person_id, locale in rows:
        try:
            Locale.parse(locale)
        except (UnknownLocaleError, ValueError, TypeError):
            invalid_ids.append(person_id)

    for person_id in invalid_ids:
        connection.execute(
            sa.text("UPDATE person SET locale = NULL WHERE id = :id"),
            {"id": person_id},
        )


def downgrade():
    # The original invalid values are intentionally not restored.
    pass
