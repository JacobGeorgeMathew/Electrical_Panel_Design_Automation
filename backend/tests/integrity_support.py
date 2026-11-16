"""Explicit administrator connection for tamper/legacy fixtures, never runtime."""
from contextlib import contextmanager
import re

from sqlalchemy import create_engine


@contextmanager
def privileged_connection(database):
    assert re.fullmatch(r'panel_integration_test_[a-f0-9]{32}', database.settings.url.database)
    engine = create_engine(database.settings.url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            yield connection
    finally:
        engine.dispose()
