import json
import re
from pathlib import Path
from uuid import uuid4
from dataclasses import replace
import pytest
from sqlalchemy import create_engine, select, text, func

from app.services.orchestrator import DesignOrchestrator
from app.services.design_errors import DesignError
from app.services.validation_engine import ValidationEngine
from app.models.pdm import PhysicalDesignModel, PhysicalComponent, Position3D, ValidationViolation
from app.repositories.enclosure_repository import EnclosureRepository
from app.persistence.repositories import MemoryEnclosures


@pytest.mark.parametrize('feeders,expected_enclosure',[(12,'ENC_800_1200_300'),(16,'ENC_1000_1200_300')])
def test_generation_satisfies_all_physical_constraints(feeders,expected_enclosure):
    package=DesignOrchestrator().generate_design('STRICT-DB',{'num_feeders':feeders},persist_requirements=False)
    pdm=package['pdm']
    assert pdm['enclosure_id']==expected_enclosure
    assert package['validation_errors']==pdm['validation_results']==[]
    assert pdm['thermal_density_index']<=pdm['validation_policy']['thermal_density_limit_w_per_l']
    terms=sorted((c for c in pdm['components'] if c['category']=='TERMINAL'),key=lambda c:c['position']['x'])
    assert min(b['position']['x']-a['position']['x']-a['width'] for a,b in zip(terms,terms[1:]))>=4-1e-6


def test_reported_terminal_gap_is_rejected_by_backend():
    def terminal(key,x):
        return PhysicalComponent(id='PDM-'+key,cem_component_id=key,name=key,category='TERMINAL',
            position=Position3D(x=x,y=20,z=20),width=8.2,height=48,depth=47,rail_id='RAIL-01',zone_name='TERMINAL',heat_loss_watts=.5,cad_model='')
    pdm=PhysicalDesignModel(id='P',project_id='P',panel_id='P',enclosure_id='E',enclosure_width=400,enclosure_height=400,enclosure_depth=200,ip_rating='IP54',
        components=[terminal('X001',20),terminal('X002',30)])
    failures=ValidationEngine().validate_pdm(pdm)
    assert any(v.type=='CLEARANCE' and v.severity=='CRITICAL' and v.required_value==4 and abs(v.actual_value-1.8)<.01 for v in failures)


def test_thermal_check_uses_unrounded_density():
    pdm=PhysicalDesignModel(id='P',project_id='P',panel_id='P',enclosure_id='E',enclosure_width=1000,enclosure_height=1000,enclosure_depth=1000,
        ip_rating='IP54',total_heat_loss_watts=450.1)
    failures=ValidationEngine().validate_pdm(pdm)
    assert any(v.type=='THERMAL' and v.severity=='CRITICAL' and v.actual_value>.45 for v in failures)


def test_undersized_fixed_enclosure_is_not_silently_replaced():
    rows=EnclosureRepository().get_all()
    engine=DesignOrchestrator(enclosure_repo=MemoryEnclosures(rows,'ENC_800_1000_300'))
    with pytest.raises(DesignError) as error: engine.generate_design('PINNED',persist_requirements=False)
    assert error.value.code=='NO_FEASIBLE_ENCLOSURE'
    assert error.value.details['minimum_volume_litres']>240


def test_generation_retries_next_enclosure_after_physical_failure(monkeypatch):
    engine=DesignOrchestrator();real=engine._physical_design;tried=[]
    def attempt(cem,components,nets,enclosure,heat):
        tried.append(enclosure.id)
        if len(tried)==1:raise DesignError('ROUTING_INFEASIBLE','Injected blocked duct route.')
        return real(cem,components,nets,enclosure,heat)
    monkeypatch.setattr(engine,'_physical_design',attempt)
    design=engine.generate_design('RETRY',persist_requirements=False)
    assert tried==['ENC_800_1200_300','ENC_1000_1200_300']
    assert design['pdm']['enclosure_id']==tried[-1] and design['validation_errors']==[]


def test_even_warning_violations_cannot_be_published(monkeypatch):
    engine=DesignOrchestrator()
    monkeypatch.setattr(engine.validation_engine,'validate_pdm',lambda *args:[ValidationViolation(type='CLEARANCE',severity='WARNING',object_a='X001',required_value=4,actual_value=1.8,unit='mm',message='Injected warning')])
    with pytest.raises(DesignError) as error:engine.generate_design('NO-WARNINGS',persist_requirements=False)
    assert error.value.code=='PHYSICAL_VALIDATION_FAILED'


def test_seed_is_idempotent_and_failed_fixed_generation_preserves_project(api,postgres_database):
    from app.persistence.seed_constraints import seed_constraints
    from app.persistence import models as m
    with postgres_database.sessions() as s:
        before=s.scalar(select(func.count()).select_from(m.design_rule_versions))
    seed_constraints(postgres_database);seed_constraints(postgres_database)
    with postgres_database.sessions() as s:
        assert s.scalar(select(func.count()).select_from(m.design_rule_versions))==before
        assert s.scalar(text('SELECT version_num FROM alembic_version'))=='0003_constraints'
    p=api.post('/api/projects',json={'name':'Strict constraints'}).json();key=p['id']
    design=api.post('/api/projects/'+key+'/revisions',json={'expected_version':p['lock_version']})
    assert design.status_code==201,design.text
    saved=design.json()
    assert saved['pdm']['validation_policy']['din_clearance_mm']==4
    assert saved['validation_errors']==[] and api.get('/api/projects/'+key+'/design').json()['is_stale'] is False
    rejected=api.post('/api/projects/'+key+'/revisions',json={'expected_version':saved['lock_version'],
        'configuration':{'enclosure_id':'ENC_800_1000_300'}})
    assert rejected.status_code==422
    current=api.get('/api/projects/'+key).json()
    assert current['current_revision_id']==saved['revision_id'] and current['lock_version']==saved['lock_version']


def test_existing_0002_database_migrates_without_rewriting_history(postgres_database):
    from app.persistence.config import Settings
    from app.persistence.database import Database
    from app.persistence.manage import alembic_config
    from app.persistence.seed_constraints import seed_constraints
    from alembic import command
    settings=Settings.load();name='panel_policy_upgrade_'+uuid4().hex
    assert re.fullmatch(r'panel_policy_upgrade_[a-f0-9]{32}',name)
    admin=create_engine(settings.url.set(database='postgres'),isolation_level='AUTOCOMMIT',hide_parameters=True)
    db=None
    try:
        with admin.connect() as c:c.exec_driver_sql('CREATE DATABASE "'+name+'"')
        cfg=alembic_config(settings.url.set(database=name));command.upgrade(cfg,'0002_app')
        db=Database(replace(settings,url=settings.url.set(database=name)))
        sql=Path(__file__).parents[2].joinpath('docs/database/002_sample_data.sql').read_text(encoding='utf-8')
        sql=re.sub(r'(?m)^(BEGIN|COMMIT);\s*$','',sql)
        with db.engine.begin() as c:c.exec_driver_sql(sql)
        with db.engine.connect() as c:
            original=[tuple(r) for r in c.execute(text('SELECT id,project_id,revision_no,content_sha256,model_manifest FROM project_revisions ORDER BY id'))]
            snapshots=[tuple(r) for r in c.execute(text('SELECT project_revision_id,sha256,snapshot FROM cem_snapshots ORDER BY project_revision_id'))]
        command.upgrade(cfg,'head');seed_constraints(db);seed_constraints(db)
        assert db.ready()
        with db.engine.connect() as c:
            assert original==[tuple(r) for r in c.execute(text('SELECT id,project_id,revision_no,content_sha256,model_manifest FROM project_revisions ORDER BY id'))]
            assert snapshots==[tuple(r) for r in c.execute(text('SELECT project_revision_id,sha256,snapshot FROM cem_snapshots ORDER BY project_revision_id'))]
            assert c.scalar(text("SELECT count(*) FROM rule_set_versions sv JOIN rule_sets s ON s.id=sv.rule_set_id WHERE s.code='DB_ENGINE_V1' AND sv.version_no=2"))==1
    finally:
        if db:db.close()
        with admin.connect() as c:c.exec_driver_sql('DROP DATABASE IF EXISTS "'+name+'" WITH (FORCE)')
        admin.dispose()
