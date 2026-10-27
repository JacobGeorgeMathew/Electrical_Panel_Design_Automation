import copy
import hashlib
import json
import struct
import time
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import func,select
from app.persistence import models as m
from app.persistence.assets import AssetStore,AssetUnavailable,primitive_glb,content_hash
from app.persistence.repositories import identifier
from app.persistence.parameters import resolve_parameters

VALUES={'supply_voltage':415,'phases':3,'frequency':50,'incomer_rating':250,'num_feeders':12,
        'ip_rating':'IP54','spare_capacity_pct':20,'neutral_required':True}


def checked(response,status=200):
    assert response.status_code==status,response.text
    return response.json()


def create(api):
    return checked(api.post('/api/projects',json={'name':'PostgreSQL workflow','requirements':VALUES}),201)


def test_catalog_readiness_and_pagination(api):
    assert api.get('/ready').status_code==200
    archetypes=checked(api.get('/api/archetypes'))
    assert any(a['code']=='DB' and a['supported'] for a in archetypes)
    page=checked(api.get('/api/components?category=MCB&page_size=2'))
    assert len(page['items'])==2 and page['total']>=3
    component=checked(api.get('/api/components/MCB_16A_1P_10KA'))
    assert component['terminals'] and component['cad_models'][0]['assets'][0]['status']=='READY'
    assert checked(api.get('/api/components/'+component['id']+'/versions'))[0]['version_no']==1
    assert checked(api.get('/api/archetypes/DB/questionnaire'))['questions']
    assert checked(api.get('/api/rules'))


def test_workflow_reopens_snapshots_projections_and_artifacts(api,postgres_database):
    p=create(api); key=p['id']
    questions=checked(api.get(f'/api/projects/{key}/requirements/questions'))
    assert any(q['id']=='phases' for q in questions)
    p=checked(api.put(f'/api/projects/{key}/answers',json={'expected_version':p['lock_version'],'answers':VALUES}))
    assert checked(api.get(f'/api/projects/{key}/answers'))['answers']['incomer_rating']==250
    design=checked(api.post(f'/api/projects/{key}/revisions',json={'expected_version':p['lock_version'],'requirements':{}}),201)
    reopened=checked(api.get(f'/api/projects/{key}/design'))
    assert reopened['cem']==design['cem'] and reopened['pdm']==design['pdm']
    rid=design['revision_id']
    with postgres_database.sessions() as s:
        assert s.scalar(select(func.count()).select_from(m.cem_component_instances).where(m.cem_component_instances.c.project_revision_id==identifier(rid)))==len(design['cem']['components'])+1
        assert s.scalar(select(func.count()).select_from(m.pdm_routes).where(m.pdm_routes.c.project_revision_id==identifier(rid)))==len(design['pdm']['routes'])
        rows=s.execute(select(m.cem_conductors).join(m.cem_nets,m.cem_nets.c.id==m.cem_conductors.c.net_id).where(m.cem_nets.c.project_revision_id==identifier(rid))).mappings().all()
        assert len(rows)==len(design['cem']['connections'])
        assert all(r['from_terminal_instance_id'] and r['to_terminal_instance_id'] for r in rows)
    preview=next(a for a in design['artifacts'] if a['file_format']=='GLB')
    file=api.get(preview['url'])
    assert file.status_code==200 and file.content[:4]==b'glTF'
    assert hashlib.sha256(file.content).hexdigest()==preview['sha256']
    node=shutil.which('node')
    if node:
        with postgres_database.sessions() as s:
            asset=s.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.id==identifier(preview['id']))).mappings().one()
        script=Path(__file__).resolve().parents[2]/'frontend/scripts/verify-glb.mjs'
        verified=subprocess.run([node,str(script),str(postgres_database.settings.asset_root/asset['storage_key'])],capture_output=True,text=True,timeout=30)
        assert verified.returncode==0,verified.stdout+verified.stderr
    validation=checked(api.get(f'/api/projects/{key}/validation'))
    assert validation['results'] and validation['revision_id']==rid
    invalid=api.patch(f'/api/projects/{key}',json={'expected_version':design['lock_version'],'requirements':{'num_feeders':100}})
    assert invalid.status_code==422
    assert checked(api.get(f'/api/projects/{key}'))['lock_version']==design['lock_version']
    changed=checked(api.post(f'/api/projects/{key}/design/propagate-change',json={'modified_field':'spare_capacity_pct','new_value':25,'expected_version':design['lock_version']}))
    assert changed['diff_report']['diffs'][0]['before']=='20'
    assert changed['diff_report']['diffs'][0]['after']=='25'
    restored=checked(api.post(f'/api/projects/{key}/revisions/{rid}/restore',json={'expected_version':changed['new_design']['lock_version']}),201)
    assert restored['cem']==design['cem'] and restored['pdm']==design['pdm']
    assert restored['revision_no']==3
    assert checked(api.get(f'/api/projects/{key}'))['requirements']['spare_capacity_pct']==20
    assert len(checked(api.get(f'/api/projects/{key}/revisions')))==3
    renamed=checked(api.patch(f'/api/projects/{key}',json={'expected_version':restored['lock_version'],'name':'Renamed panel'}))
    assert checked(api.get(f'/api/projects/{key}/design'))['is_stale'] is False


def test_project_dimensions_are_private_and_conflicting_writes_rejected(api):
    p=create(api)
    enclosures=checked(api.get('/api/enclosures'))
    enclosure=enclosures[-1]
    original=copy.deepcopy(enclosure)
    config={'enclosure_id':enclosure['id'],'enclosure_parameters':{'width_mm':enclosure['width']+50}}
    saved=checked(api.patch('/api/projects/'+p['id'],json={'expected_version':p['lock_version'],'configuration':config}))
    assert saved['configuration']==config
    assert checked(api.get('/api/enclosures'))==enclosures
    conflict=api.patch('/api/projects/'+p['id'],json={'expected_version':p['lock_version'],'name':'Obsolete edit'})
    assert conflict.status_code==409
    invalid=api.patch('/api/projects/'+p['id'],json={'expected_version':saved['lock_version'],'configuration':{'enclosure_id':enclosure['id'],'enclosure_parameters':{'width_mm':-10}}})
    assert invalid.status_code==422


def test_atomic_revision_rollback(api,postgres_database,monkeypatch):
    p=create(api)
    from app.services import project_service
    real=project_service.write_revision
    def broken(*args,**kwargs):
        real(*args,**kwargs)
        raise RuntimeError('Injected failure after all projection writes')
    monkeypatch.setattr(project_service,'write_revision',broken)
    with pytest.raises(RuntimeError):
        api.post('/api/projects/'+p['id']+'/design/generate',json={})
    assert checked(api.get('/api/projects/'+p['id']+'/revisions'))==[]
    assert checked(api.get('/api/projects/'+p['id']))['lock_version']==p['lock_version']


def test_background_cad_status_and_missing_assets(api,postgres_database):
    p=create(api)
    design=checked(api.post('/api/projects/'+p['id']+'/design/generate',json={}))
    job=checked(api.post('/api/projects/'+p['id']+'/cad-generation',json={'expected_version':design['lock_version'],'file_format':'GLB'}),202)
    for _ in range(40):
        status=checked(api.get(f'/api/projects/{p["id"]}/cad-generation/{job["id"]}'))
        if status['status']!='PENDING': break
        time.sleep(0.05)
    assert status['status']=='READY'
    assert api.get(status['url']).status_code==200
    with postgres_database.sessions() as s:
        row=s.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.id==identifier(job['id']))).mappings().one()
    path=postgres_database.settings.asset_root/row['storage_key']
    original=path.read_bytes()
    path.write_bytes(b'corrupt test asset')
    try:
        assert api.get(status['url']).status_code==404
        assert checked(api.get('/api/artifacts/'+job['id']))['status']=='MISSING_OR_CORRUPT'
    finally:
        path.write_bytes(original)


def test_missing_project_does_not_create_it(api):
    assert api.get('/api/projects/nonexistent').status_code==404

def test_conditional_answers_survive_hidden_requirements(api):
    p=create(api)
    saved=checked(api.put('/api/projects/'+p['id']+'/answers',json={'expected_version':p['lock_version'],'answers':{**VALUES,'phases':1,'neutral_required':False}}))
    assert checked(api.get('/api/projects/'+p['id']+'/answers'))['answers']['neutral_required'] is False
    requirements=checked(api.get('/api/projects/'+p['id']+'/requirements'))['requirements']
    assert next(r for r in requirements if r['code']=='neutral_required')['value']['value'] is None
    updated=checked(api.patch('/api/projects/'+p['id'],json={'expected_version':saved['lock_version'],'requirements':{'phases':3}}))
    assert updated['requirements']['neutral_required'] is False

def test_legacy_import_is_idempotent(postgres_database):
    from app.persistence.import_legacy import import_legacy
    with postgres_database.sessions() as s:
        count=s.scalar(select(func.count()).select_from(m.component_versions))
    import_legacy(postgres_database)
    with postgres_database.sessions() as s:
        assert s.scalar(select(func.count()).select_from(m.component_versions))==count
        versions=list(s.scalars(select(m.functional_module_versions.c.version_no).join(m.functional_modules,m.functional_modules.c.id==m.functional_module_versions.c.module_id)
            .where(m.functional_modules.c.code=='INCOMER').order_by(m.functional_module_versions.c.version_no)))
        assert versions==[1,2]


def test_asset_integrity_and_traversal(tmp_path):
    store=AssetStore(tmp_path/'assets')
    file=store.put(b'hello','json')
    assert store.verified_path(file['storage_key'],file['sha256']).read_bytes()==b'hello'
    with pytest.raises(AssetUnavailable): store.verified_path('../outside',file['sha256'])
    with pytest.raises(AssetUnavailable): store.verified_path(file['storage_key'],'0'*64)


def test_parameter_units_fixed_values_and_dependency_cycles():
    defs=[{'code':'width','value_type':'DECIMAL','unit_code':'mm','default_value':100,'editable':True,'derived':False,'min_value':1},
          {'code':'usable','value_type':'DECIMAL','unit_code':'mm','derived':True,'editable':False,'expression':'width - 20','dependencies':['width']}]
    assert resolve_parameters(defs,{'width':{'value':0.2,'unit':'m'}})['usable']==180
    with pytest.raises(Exception): resolve_parameters(defs,{'usable':10})
    defs[1]['dependencies']=['usable']
    with pytest.raises(Exception): resolve_parameters(defs,{})


def test_readiness_failure_is_safe():
    from fastapi.testclient import TestClient
    from app.main import create_app
    class BrokenDB:
        def ready(self): return False
        def close(self): pass
    with TestClient(create_app(BrokenDB())) as client:
        response=client.get('/ready')
        assert response.status_code==503 and 'NOT_READY' in response.text

def test_orm_metadata_matches_migrated_schema(postgres_database):
    from alembic import command
    from app.persistence.manage import alembic_config
    command.check(alembic_config(postgres_database.settings.url))

def test_database_connection_errors_do_not_leak_configuration(postgres_database):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.persistence.database import Database
    broken=Database(replace(postgres_database.settings,url=postgres_database.settings.url.set(port=1),connect_timeout=1))
    with TestClient(create_app(broken)) as client:
        assert client.get('/ready').status_code==503
        response=client.get('/api/projects')
        assert response.status_code==503
        assert 'DATABASE_UNAVAILABLE' in response.text
        assert 'postgresql://' not in response.text.lower()
