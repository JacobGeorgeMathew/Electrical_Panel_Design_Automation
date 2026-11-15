"""Contract checks only: no database writes or engine execution."""
import copy
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.document import DocumentSnapshots, ResolvedDocument, snapshot_sha256

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/document-v1.json'


def document_fixture():
    """Create deterministic fixture with preserved logical IDs and nonzero offsets."""
    requirement = dict(id='voltage', label='Supply voltage', value=415, unit='V',
                       state='CONFIRMED', source='USER', message=None)
    component = dict(id='QF001', catalog_id='MCB-01', name='Outgoing', category='MCB',
                     current_rating=32, breaking_capacity=6, poles=1, width=18, height=80,
                     depth=70, mounting='DIN', heat_loss=2, cad_model='mcb',
                     terminals=[dict(id='OUT', x=9, y=80, z=35)])
    connection = dict(id='N-PE-C01', from_component='QF001', from_terminal='OUT',
                      to_component='PANEL_ROOT', to_terminal='EARTH_STUD', net_id='N-PE', wire_class='PE')
    snapshots = DocumentSnapshots.model_validate(dict(
        requirements=dict(project_id='project-1', archetype='DB', items=[requirement]),
        cem=dict(project_id='project-1', panel_id='panel-1', requirements=[requirement],
                 components=[component], connections=[connection],
                 nets=[dict(id='N-PE', name='PE', voltage_level=0, wire_class='PE', connections=[connection])],
                 physical_design_id='pdm-1'),
        pdm=dict(id='pdm-1', project_id='project-1', panel_id='panel-1', enclosure_id='ENC-1',
                 enclosure_width=600, enclosure_height=800, enclosure_depth=250, ip_rating='IP54',
                 mounting_plate_x=25, mounting_plate_y=30, mounting_plate_z=20,
                 zones=[dict(name='DIN', x_min=25, x_max=575, y_min=30, y_max=770)],
                 rails=[dict(id='rail-1', label='Rail', x=50, y=200, z=30, length=500)],
                 components=[dict(id='PDM-QF001', cem_component_id='QF001', name='Outgoing', category='MCB',
                                  position=dict(x=125.5, y=200.25, z=37.5), width=18, height=80, depth=70,
                                  rail_id='rail-1', zone_name='DIN', heat_loss_watts=2, cad_model='mcb',
                                  terminals=[dict(id='OUT', x=134.5, y=280.25, z=72.5)])],
                 ducts=[dict(id='duct-1', label='Duct', x=50, y=300, z=20, width=500, height=40, depth=40,
                             route_ids=['route-1'])],
                 routes=[dict(id='route-1', conductor_id='N-PE-C01', net_id='N-PE', net_name='PE',
                              from_component='QF001', from_terminal='OUT', to_component='PANEL_ROOT',
                              to_terminal='EARTH_STUD', wire_class='PE', length_mm=100, bend_count=0,
                              duct_ids=['duct-1'], waypoints=[dict(x=134.5, y=280.25, z=72.5), dict(x=134.5, y=380.25, z=72.5)])]),
        schematic=dict(id='schematic-1', project_id='project-1', panel_id='panel-1', page_id='page-1',
                       width_mm=1200, height_mm=1000,
                       symbols=[dict(id='symbol-1', component_id='QF001', position=dict(x=100, y=100),
                                     width_mm=100, height_mm=70, pins=[dict(id='pin-1', terminal_id='OUT',
                                     position=dict(x=150, y=170), direction='BOTTOM')]),
                                dict(id='symbol-2', component_id='PANEL_ROOT', position=dict(x=100, y=300),
                                     width_mm=100, height_mm=70, pins=[dict(id='pin-2', terminal_id='EARTH_STUD',
                                     position=dict(x=150, y=300), direction='TOP')])],
                       wires=[dict(id='wire-1', conductor_id='N-PE-C01', source_pin_id='pin-1', target_pin_id='pin-2',
                                   waypoints=[dict(x=150, y=170), dict(x=150, y=300)])])
    ))
    return ResolvedDocument.model_validate(dict(
        document=dict(document_id='document-1', project_id='project-1', panel_id='panel-1', document_sequence=7,
                      lock_version=3, models={kind: dict(sha256=snapshot_sha256(getattr(snapshots, kind)))
                                              for kind in ('requirements', 'cem', 'pdm', 'schematic')},
                      pins=dict(engine_version='db-pipeline-4', generator=dict(name='panelstudio-primitives', version='3'),
                                catalog_manifest_sha256='a' * 64, validation_policy_version='strict-v1'),
                      provenance=dict(origin='MANUAL', actor_id='local-user'), dirty_stages=['routes', 'cad'],
                      enclosure_interfaces=[dict(component_id='PANEL_ROOT', terminal_ids=['EARTH_STUD'])]),
        snapshots=snapshots))


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text())


def rehash(payload):
    snapshots = DocumentSnapshots.model_validate(payload['snapshots'])
    for kind in ('requirements', 'cem', 'pdm', 'schematic'):
        snapshot = getattr(snapshots, kind)
        payload['document']['models'][kind] = None if snapshot is None else dict(schema_version=1, sha256=snapshot_sha256(snapshot))
    return payload


def test_fixture_round_trip(payload):
    model = ResolvedDocument.model_validate(payload)
    assert json.loads(model.model_dump_json()) == payload
    assert document_fixture() == model
    assert model.snapshots.requirements.items[0].state.value == 'CONFIRMED'
    assert model.snapshots.pdm.components[0].position.model_dump() == dict(x=125.5, y=200.25, z=37.5)
    assert model.snapshots.pdm.mounting_plate_x == 25
    assert model.snapshots.schematic.wires[0].conductor_id == model.snapshots.cem.connections[0].id


@pytest.mark.parametrize('state', ['MISSING', 'PROPOSED', 'CONFIRMED', 'VALIDATED', 'DERIVED', 'CALCULATED', 'ASSUMED', 'CONFLICTING'])
def test_requirement_states_survive(payload, state):
    for item in (payload['snapshots']['requirements']['items'][0], payload['snapshots']['cem']['requirements'][0]):
        item['state'] = state
        item['source'] = 'DERIVED'
        item['message'] = 'Preserve provenance'
    model = ResolvedDocument.model_validate(rehash(payload))
    assert json.loads(model.model_dump_json()) == payload


@pytest.mark.parametrize(('section', 'field', 'value', 'code'), [
    ('document', 'schema_version', '2.0.0', 'literal_error'),
    ('document', 'document_sequence', -1, 'greater_than_equal'),
    ('document', 'document_sequence', True, 'int_type'),
    ('document', 'document_id', ' QF001 ', 'invalid_stable_id'),
    ('document', 'unknown_field', 1, 'extra_forbidden'),
])
def test_document_rejections(payload, section, field, value, code):
    payload[section][field] = value
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(payload)
    assert error.value.errors()[0]['type'] == code


@pytest.mark.parametrize('target', ['cem', 'pdm', 'schematic', 'requirements'])
def test_reference_schema_rejected(payload, target):
    payload['document']['models'][target]['schema_version'] = 2
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(payload)
    assert error.value.errors()[0]['type'] == 'literal_error'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('target', ['position', 'rotation', 'nested_geometry', 'schematic', 'configuration', 'coerced_dimension'])
def test_nonfinite_rejections(payload, value, target):
    component = payload['snapshots']['pdm']['components'][0]
    if target == 'position':
        component['position']['x'] = value
    elif target == 'rotation':
        component['rotation_deg'] = value
    elif target == 'nested_geometry':
        component['geometry'] = [{'position': {'x': value}}]
    elif target == 'schematic':
        payload['snapshots']['schematic']['symbols'][0]['position']['x'] = value
    elif target == 'coerced_dimension':
        payload['snapshots']['pdm']['enclosure_width'] = str(value)
    else:
        payload['document']['configuration'] = {'offset': value}
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(payload)
    assert error.value.errors()[0]['type'] == 'nonfinite_value'
    assert 'path' in error.value.errors()[0]['ctx']


@pytest.mark.parametrize('target', ['component', 'terminal', 'net', 'physical', 'rail', 'duct', 'route', 'symbol', 'pin_terminal', 'wire', 'interface'])
def test_unknown_references(payload, target):
    s = payload['snapshots']
    if target in ('component', 'terminal', 'net'):
        field = {'component': 'from_component', 'terminal': 'from_terminal', 'net': 'net_id'}[target]
        s['cem']['connections'][0][field] = 'missing'
    elif target == 'physical':
        s['pdm']['components'][0]['cem_component_id'] = 'missing'
    elif target == 'rail':
        s['pdm']['components'][0]['rail_id'] = 'missing'
    elif target == 'duct':
        s['pdm']['routes'][0]['duct_ids'] = ['missing']
    elif target == 'route':
        s['pdm']['ducts'][0]['route_ids'] = ['missing']
    elif target == 'symbol':
        s['schematic']['symbols'][0]['component_id'] = 'missing'
    elif target == 'pin_terminal':
        s['schematic']['symbols'][0]['pins'][0]['terminal_id'] = 'missing'
    elif target == 'wire':
        s['schematic']['wires'][0]['conductor_id'] = 'missing'
    else:
        payload['document']['enclosure_interfaces'] = []
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(rehash(payload))
    assert error.value.errors()[0]['type'] == 'unknown_reference'
    assert 'reference' in error.value.errors()[0]['ctx']


def test_presentation_does_not_change_connectivity(payload):
    before = copy.deepcopy(payload['snapshots']['cem'])
    payload['snapshots']['schematic']['symbols'][0]['position']['x'] += 50
    payload['snapshots']['schematic']['wires'][0]['waypoints'].insert(1, {'x': 90, 'y': 200})
    model = ResolvedDocument.model_validate(rehash(payload))
    assert model.snapshots.cem.model_dump(mode='json') == before


@pytest.mark.parametrize('target', ['hash', 'owner', 'membership', 'route_endpoint', 'wire_endpoint', 'duplicate', 'missing_snapshot'])
def test_integrity_failures(payload, target):
    if target == 'hash':
        payload['document']['models']['pdm']['sha256'] = '0' * 64
    else:
        if target == 'owner':
            payload['snapshots']['pdm']['project_id'] = 'another-project'
        elif target == 'membership':
            payload['snapshots']['cem']['nets'][0]['connections'][0]['from_terminal'] = 'other'
        elif target == 'route_endpoint':
            payload['snapshots']['pdm']['routes'][0]['from_terminal'] = 'other'
        elif target == 'wire_endpoint':
            payload['snapshots']['schematic']['wires'][0]['source_pin_id'] = 'pin-2'
        elif target == 'duplicate':
            payload['snapshots']['cem']['components'] *= 2
        elif target == 'missing_snapshot':
            payload['snapshots']['pdm'] = None
        if target != 'missing_snapshot':
            rehash(payload)
    with pytest.raises(ValidationError):
        ResolvedDocument.model_validate(payload)


def test_input_only_document(payload):
    for kind in ('cem', 'pdm', 'schematic'):
        payload['document']['models'][kind] = None
        payload['snapshots'][kind] = None
    assert ResolvedDocument.model_validate(payload).snapshots.cem is None


def test_pinned_policy_version(payload):
    payload['document']['pins']['validation_policy_version'] = 'future-policy'
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(payload)
    assert error.value.errors()[0]['type'] == 'version_pin_mismatch'


def test_unknown_accessory_parent(payload):
    payload['snapshots']['pdm']['accessories'] = [dict(
        id='handle-1', catalog_id='handle', name='Handle', category='HARDWARE', parent_id='missing',
        position=dict(x=10, y=20, z=30), width=10, height=10, depth=10)]
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(rehash(payload))
    assert error.value.errors()[0]['type'] == 'unknown_reference'


@pytest.mark.parametrize('value', [True, '1', 1.0])
def test_snapshot_schema_does_not_coerce(payload, value):
    payload['document']['models']['cem']['schema_version'] = value
    with pytest.raises(ValidationError) as error:
        ResolvedDocument.model_validate(payload)
    assert error.value.errors()[0]['type'] == 'unsupported_schema_version'


def test_openapi_and_structured_errors(payload):
    app = FastAPI()

    @app.post('/contract', response_model=ResolvedDocument)
    def contract(value: ResolvedDocument):
        return value

    client = TestClient(app)
    assert client.post('/contract', json=payload).json() == payload
    schema = app.openapi()['components']['schemas']
    assert schema['WorkingDocument']['properties']['schema_version']['const'] == '1.0.0'
    assert schema['SchematicPresentation']['additionalProperties'] is False
    payload['snapshots']['schematic']['wires'][0]['target_pin_id'] = 'unknown'
    error = client.post('/contract', json=payload)
    assert error.status_code == 422
    assert error.json()['detail'][0]['type'] == 'unknown_reference'
    assert error.json()['detail'][0]['ctx']['reference'] == 'unknown'
