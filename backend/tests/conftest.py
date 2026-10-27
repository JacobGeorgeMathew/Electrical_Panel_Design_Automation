import os
import re
from dataclasses import replace
from uuid import uuid4
import pytest
from sqlalchemy import create_engine


@pytest.fixture(scope='session')
def postgres_database(tmp_path_factory):
    if os.environ.get('PANEL_RUN_POSTGRES_TESTS')!='1':
        pytest.skip('Set PANEL_RUN_POSTGRES_TESTS=1 to exercise a unique isolated PostgreSQL database.')
    from app.persistence.config import Settings
    from app.persistence.database import Database
    from app.persistence.manage import initialize
    from app.persistence.import_legacy import import_legacy
    settings=Settings.load()
    name='panel_integration_test_'+uuid4().hex
    assert re.fullmatch(r'panel_integration_test_[a-f0-9]{32}',name)
    admin=create_engine(settings.url.set(database='postgres'),isolation_level='AUTOCOMMIT',hide_parameters=True)
    db=None
    try:
        with admin.connect() as c: c.exec_driver_sql(f'CREATE DATABASE "{name}"')
        db=Database(replace(settings,url=settings.url.set(database=name),asset_root=tmp_path_factory.mktemp('panel-assets')))
        initialize(db)
        # Match the actual existing development database, including its published SQL fixture.
        from pathlib import Path
        source=Path(__file__).resolve().parents[2]/'docs/database/002_sample_data.sql'
        sql=re.sub(r'(?m)^(BEGIN|COMMIT);\s*$','',source.read_text(encoding='utf-8'))
        with db.engine.begin() as conn: conn.exec_driver_sql(sql)
        import_legacy(db)
        yield db
    finally:
        if db: db.close()
        with admin.connect() as c: c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.fixture
def api(postgres_database):
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(postgres_database)) as client:
        yield client
