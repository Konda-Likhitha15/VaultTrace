"""Alembic environment configured from application settings."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base
from app import models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
if settings.alembic_use_production_database:
    if settings.production_database_url is None:
        raise RuntimeError(
            "ALEMBIC_USE_PRODUCTION_DATABASE is enabled, but PRODUCTION_DATABASE_URL is not set"
        )
    database_url = settings.production_database_url.get_secret_value()
else:
    database_url = settings.database_url

url = make_url(database_url)
if url.drivername == "postgresql":
    # requirements.txt installs Psycopg 3, not the default Psycopg 2 driver.
    database_url = url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a configured SQLAlchemy connection."""
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
