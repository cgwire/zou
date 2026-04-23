import logging

from alembic import context
from sqlalchemy import create_engine, pool
from logging.config import fileConfig

config = context.config

# Detect whether we're running inside a Flask app context
# (flask_migrate.upgrade) or standalone (alembic.command.upgrade).
try:
    from flask import current_app

    url = current_app.config["SQLALCHEMY_DATABASE_URI"]
    db = current_app.extensions["migrate"].db
    target_metadata = db.metadata
    migrate_args = current_app.extensions["migrate"].configure_args
except RuntimeError:
    # No Flask app context — read URL from Alembic config.
    # target_metadata is only needed for autogenerate (migrate_db),
    # which always runs with a Flask context.
    url = config.get_main_option("sqlalchemy.url")
    target_metadata = None
    migrate_args = {}

if config.config_file_name:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def include_object(object, name, type_, reflected, compare_to):
    if target_metadata is not None and type_ == "table":
        return not reflected or name in target_metadata.tables
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
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            render_item=render_item,
            include_object=include_object,
            **migrate_args,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
