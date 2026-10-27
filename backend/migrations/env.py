from alembic import context
from sqlalchemy import create_engine, pool
from app.persistence.config import Settings
from app.persistence.models import metadata

config = context.config
url = config.attributes.get("database_url") or Settings.load().url

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
