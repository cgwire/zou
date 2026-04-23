import logging

from alembic import context
from sqlalchemy import create_engine, pool
from logging.config import fileConfig
from flask import current_app

db = current_app.extensions["migrate"].db

# Database URL (passed by Alembic)
config = context.config
url = current_app.config.get("SQLALCHEMY_DATABASE_URI")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return not reflected or name in db.metadata.tables
    return True


def render_item(type_, obj, autogen_context):
    """Apply custom rendering for selected items."""

    import sqlalchemy_utils

    if type_ == "type" and isinstance(
        obj, sqlalchemy_utils.types.uuid.UUIDType
    ):
        autogen_context.imports.add("import sqlalchemy_utils")
        autogen_context.imports.add("import uuid")
        return "sqlalchemy_utils.types.uuid.UUIDType(binary=False), default=uuid.uuid4"

    return False


def process_revision_directives(context, revision, directives):
    if getattr(config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("No changes in schema detected.")


def run_migrations_online():
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=db.metadata,
            process_revision_directives=process_revision_directives,
            render_item=render_item,
            include_object=include_object,
            **current_app.extensions["migrate"].configure_args,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
