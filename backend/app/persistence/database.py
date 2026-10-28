from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.persistence.config import Settings


class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_engine(settings.url, pool_pre_ping=True, pool_size=settings.pool_size,
            max_overflow=settings.max_overflow, pool_timeout=5, echo=False, hide_parameters=True,
            connect_args={"connect_timeout": settings.connect_timeout, "application_name": "panelstudio"})
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def ready(self) -> bool:
        try:
            with self.engine.connect() as conn:
                return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0003_constraints"
        except Exception:
            return False

    def close(self):
        self.engine.dispose()
