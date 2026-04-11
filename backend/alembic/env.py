from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv
import os

load_dotenv()

from backend.db.base import Base
from backend.db import models  # noqa: F401

config = context.config

# ENV'den DATABASE_URL oku — alembic.ini'deki URL'yi override et
db_url = os.getenv("DATABASE_URL") or (
    f"postgresql://{os.getenv('DB_USER','postgres')}:"
    f"{os.getenv('DB_PASSWORD','')}@"
    f"{os.getenv('DB_HOST','localhost')}:"
    f"{os.getenv('DB_PORT','5432')}/"
    f"{os.getenv('DB_NAME','manifetch')}"
)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()