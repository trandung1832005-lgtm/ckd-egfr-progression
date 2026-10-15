from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from server import config as app_config
from server.db import Base
from server import models  # noqa: F401  (đăng ký các bảng vào metadata)

cfg = context.config
if cfg.config_file_name:
    fileConfig(cfg.config_file_name)
cfg.set_main_option("sqlalchemy.url", app_config.DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata
IS_SQLITE = app_config.DATABASE_URL.startswith("sqlite")


def run_migrations_offline():
    context.configure(url=app_config.DATABASE_URL, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=IS_SQLITE)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(cfg.get_section(cfg.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=IS_SQLITE)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
