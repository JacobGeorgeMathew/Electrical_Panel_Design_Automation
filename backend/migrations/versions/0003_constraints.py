"""Publish strict prototype constraint policy; preserve all earlier rule versions.

The adjacent JSON is frozen seed input for both this data migration and the
idempotent seed-constraints CLI. No geometry assets or private configuration.
"""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from alembic import op
from sqlalchemy import text

revision = '0003_constraints'
down_revision = '0002_app'
branch_labels = None
depends_on = None


def uid(key):
    return uuid5(NAMESPACE_URL,'panelstudio:constraints-v1:'+key)


def legacy_uid(key):
    return uuid5(NAMESPACE_URL,'panelstudio:legacy:'+key)


def seed(connection):
    source=json.loads(Path(__file__).with_name('0003_constraints.seed.json').read_text(encoding='utf-8'))
    connection.execute(text('INSERT INTO rule_sets(id,code,name) VALUES (:id,:code,:name) ON CONFLICT(code) DO NOTHING'),
        {'id':legacy_uid('rule-set'),'code':'DB_ENGINE_V1','name':'DB prototype engine rules (unverified)'})
    rule_set=connection.execute(text("SELECT id FROM rule_sets WHERE code='DB_ENGINE_V1'")).scalar_one()
    target=uid('rule-set-version-2')
    connection.execute(text("INSERT INTO rule_set_versions(id,rule_set_id,version_no,status) VALUES (:id,:parent,2,'PUBLISHED') ON CONFLICT(id) DO NOTHING"),
        {'id':target,'parent':rule_set})
    entries=[('DB_LAYOUT_CONFIG',legacy_uid('rule:DB_LAYOUT_CONFIG'),'prototype_metadata',2,uid('layout-version-2'),
        {'id':'DB_LAYOUT_CONFIG','name':'Strict layout configuration','category':'LAYOUT','layout_config':source['layout_config']}),
        ('DB_CONSTRAINT_POLICY',uid('policy-rule'),'db_constraints_v1',1,uid('policy-version-1'),source['policy'])]
    for code,rid,handler,version,vid,parameters in entries:
        connection.execute(text('INSERT INTO design_rules(id,code,name,engine_handler) VALUES (:id,:code,:name,:handler) ON CONFLICT(code) DO NOTHING'),
            {'id':rid,'code':code,'name':code.replace('_',' ').title(),'handler':handler})
        rid=connection.execute(text('SELECT id FROM design_rules WHERE code=:code'),{'code':code}).scalar_one()
        existing=connection.execute(text('SELECT parameters FROM design_rule_versions WHERE id=:id'),{'id':vid}).scalar_one_or_none()
        if existing is not None and existing!=parameters:
            raise RuntimeError('Published constraint seed differs; create a new versioned migration.')
        connection.execute(text("""INSERT INTO design_rule_versions(id,rule_id,version_no,status,severity,hardness,parameters,provenance)
            VALUES (:id,:rule,:version,'PUBLISHED','ERROR','HARD',CAST(:parameters AS jsonb),CAST(:provenance AS jsonb)) ON CONFLICT(id) DO NOTHING"""),
            {'id':vid,'rule':rid,'version':version,'parameters':json.dumps(parameters),
             'provenance':json.dumps({'source':'0003_constraints.seed.json','prototype':True,'verified':False,'seed_version':source['seed_version']})})
        connection.execute(text('INSERT INTO rule_set_members(rule_set_version_id,rule_version_id) VALUES (:target,:version) ON CONFLICT DO NOTHING'),
            {'target':target,'version':vid})
        connection.execute(text("INSERT INTO rule_applicability(id,rule_version_id,target_kind,predicate) VALUES (:id,:version,'DESIGN',CAST(:predicate AS jsonb)) ON CONFLICT DO NOTHING"),
            {'id':uid('applicability:'+code),'version':vid,'predicate':json.dumps({'archetype':'DB'})})
    # Fresh installs import the original catalog after migrations. Running this
    # seed again then attaches its remaining validation rules to the new set.
    connection.execute(text("""INSERT INTO rule_set_members(rule_set_version_id,rule_version_id,enabled)
        SELECT :target,member.rule_version_id,member.enabled
        FROM rule_set_members member JOIN rule_set_versions sv ON sv.id=member.rule_set_version_id
        JOIN design_rule_versions rv ON rv.id=member.rule_version_id JOIN design_rules r ON r.id=rv.rule_id
        WHERE sv.rule_set_id=:parent AND sv.version_no=1 AND r.code<>'DB_LAYOUT_CONFIG'
        ON CONFLICT DO NOTHING"""),{'target':target,'parent':rule_set})
    return {'rule_set':'DB_ENGINE_V1','version':2,'constraint_policy':'strict-v1'}


def upgrade():
    seed(op.get_bind())


def downgrade():
    raise RuntimeError('Published rules may be pinned by saved revisions; use a reviewed forward migration.')
