import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem

from src.core.config import settings
from src.db.base import Base
from src.models import *  # noqa: F403

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def include_object(
    object: SchemaItem, name: str | None, type_: str, reflected: bool, compare_to: SchemaItem | None
) -> bool:
    postgis_tables = {
        "spatial_ref_sys",
        "topology",
        "layer",
        "addr",
        "state",
        "county",
        "place",
        "zip_lookup",
        "street_type_lookup",
        "direction_lookup",
        "secondary_unit_lookup",
        "countysub_lookup",
        "county_lookup",
        "place_lookup",
        "zip_state",
        "zip_state_loc",
        "geocode_settings",
        "geocode_settings_default",
        "pagc_gaz",
        "pagc_lex",
        "pagc_rules",
        "bg",
        "loader_platform",
        "loader_variables",
        "loader_lookuptables",
        "state_lookup",
        "zip_lookup_base",
        "zip_lookup_all",
        "tabblock",
        "tabblock20",
        "tract",
        "zcta5",
        "cousub",
        "featnames",
        "edges",
        "faces",
        "addrfeat",
    }

    if type_ == "table" and name in postgis_tables:
        return False

    if type_ == "index" and hasattr(object, "table"):
        obj_any: Any = object
        if obj_any.table.name in postgis_tables:
            return False

    obj_schema = getattr(object, "schema", None)
    if obj_schema is None and hasattr(object, "table"):
        obj_schema = getattr(getattr(object, "table", None), "schema", None)

    if obj_schema in ["tiger", "tiger_data", "topology"]:
        return False

    return True


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
