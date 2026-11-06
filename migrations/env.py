from logging.config import fileConfig

from alembic import context

from affiliate_data import models  # noqa: F401  (registers the tables on Base.metadata)
from affiliate_data.db import Base, engine

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
