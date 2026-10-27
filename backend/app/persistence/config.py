import os
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import URL, make_url


class ConfigurationError(RuntimeError):
    pass


def environment(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    # A Tauri/terminal process can predate a Windows user environment change.
    if os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, name)[0]
        except OSError:
            pass
    return None


@dataclass(frozen=True)
class Settings:
    url: URL = field(repr=False)
    pool_size: int = 5
    max_overflow: int = 5
    connect_timeout: int = 5
    asset_root: Path = field(default_factory=lambda: Path(os.environ.get(
        "PANEL_DATA_DIR", str(Path.home() / ".panelstudio"))) / "assets")

    @classmethod
    def load(cls):
        explicit = environment("DATABASE_URL")
        raw = explicit or environment("PANEL_DATABASE_URL")
        if not raw:
            raise ConfigurationError("Configure DATABASE_URL or PANEL_DATABASE_URL for PostgreSQL.")
        try:
            url = make_url(raw.strip()).set(drivername="postgresql+psycopg")
            if make_url(raw.strip()).get_backend_name() not in {"postgresql", "postgres"}:
                raise ValueError()
            # The URI used to provision this project connects to the maintenance DB.
            if not explicit and url.database in {None, "postgres"}:
                url = url.set(database="electrical_panel_design")
            if url.database in {None, "postgres", "template0", "template1"}:
                raise ValueError()
            if int(os.getenv("DATABASE_POOL_SIZE", "5")) < 1 or int(os.getenv("DATABASE_MAX_OVERFLOW", "5")) < 0 or int(os.getenv("DATABASE_CONNECT_TIMEOUT", "5")) < 1:
                raise ValueError()
            return cls(url=url, pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
                       max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "5")),
                       connect_timeout=int(os.getenv("DATABASE_CONNECT_TIMEOUT", "5")))
        except (ValueError, TypeError):
            raise ConfigurationError("Invalid PostgreSQL configuration; connection details are hidden.") from None
