import importlib.util
import logging
import sys
from alembic import context
from sqlalchemy import create_engine, pool
from pathlib import Path
from logging.config import fileConfig

from zou.app.utils.plugins import PluginManifest

plugin_path = Path(__file__).resolve().parents[1]
models_path = plugin_path / "models.py"
manifest = PluginManifest.from_plugin_path(plugin_path)

module_name = f"_plugin_models_{manifest['id']}"
spec = importlib.util.spec_from_file_location(module_name, models_path)
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)

# Database URL (passed by Alembic)
config = context.config
url = config.get_main_option("sqlalchemy.url")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def include_object(object, name, type_, reflected, compare_to):
    if type_ == "table":
        return not reflected or name in module.plugin_metadata.tables
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


def run_migrations_online():
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=module.plugin_metadata,
            version_table=f"alembic_version_{manifest['id']}",
            compare_type=True,
            include_object=include_object,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
