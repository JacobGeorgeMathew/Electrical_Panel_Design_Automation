"""Detached stage equivalence, identity/reference and immutable-input contracts."""
import builtins
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.cem import ComponentRef
from app.persistence.assets import content_hash
from app.services.design_errors import DesignError
from app.services.stages.contracts import STAGE_REGISTRY
from app.services.stages.electrical import (
    CalculationsInput, ConnectivityInput, DocumentIdentities, ElectricalContext,
    IdentityBinding, PinnedComponents, PinnedRules, RequirementsInput,
    SchematicInput, SelectionInput, Snapshot, calculations_stage,
    connectivity_stage, requirements_stage, schematic_stage, selection_stage,
)
from tests.design_baseline_support import CASES, FIXTURES, engine


def supplied(case, identities=DocumentIdentities(), overrides=None):
    oracle = engine(case)
    context = ElectricalContext(project_id=case['project_id'], panel_id='DB-'+case['project_id'],
                                engine_version='fixture-engine-1', identities=identities)
    answers = {**CASES['requirements'], 'num_feeders': case['num_feeders'], **(overrides or {})}
    return RequirementsInput(context=context, answers=Snapshot[dict].capture(answers), rules=PinnedRules(
        archetype_version='fixture-db-1', rules_version='fixture-rules-1',
        template=Snapshot[dict].capture(oracle.req_engine.get_template('DB')))), PinnedComponents(
            catalog_version='fixture-components-1', rows=Snapshot[list[dict]].capture(oracle.comp_repo.get_all()))


def execute(req_input, catalog, accepted=None):
    requirements = requirements_stage(req_input)
    context = req_input.context
    calculations = calculations_stage(CalculationsInput(context=context, requirements=requirements))
    selection = selection_stage(SelectionInput(context=context, requirements=requirements,
        calculations=calculations, catalog=catalog, accepted_components=accepted))
    connectivity = connectivity_stage(ConnectivityInput(context=context, requirements=requirements, selection=selection))
    schematic = schematic_stage(SchematicInput(context=context, selection=selection, connectivity=connectivity))
    return requirements, calculations, selection, connectivity, schematic


@pytest.mark.parametrize('case', CASES['feasible'], ids=lambda c: c['id'])
def test_matches_full_generation_and_frozen_baseline(case):
    req_input, catalog = supplied(case)
    stages = execute(req_input, catalog)
    req, calc, selection, connectivity, schematic = stages
    full = engine(case).generate_design(case['project_id'], persist_requirements=False)
    cem = full['cem']
    assert req.validated_requirements.read().model_dump(mode='json')['items'] == cem['requirements']
    assert json.loads(calc.calculations.data_json) == cem['calculations']
    assert json.loads(selection.components.data_json) == cem['components']
    assert json.loads(selection.modules.data_json) == cem['modules']
    for field in ('electrical_graph', 'nets', 'connections'):
        assert json.loads(getattr(connectivity, field).data_json) == cem[field]
    assert schematic.schematic.read() == full['schematic']
    baseline = json.loads((FIXTURES / (case['id']+'.observed.json')).read_text())
    assert content_hash(full['cem']) == baseline['hashes']['cem']['sha256']
    assert content_hash(schematic.schematic.read()) == baseline['hashes']['schematic']['sha256']
    assert stages == execute(req_input, catalog)
    # Every boundary survives serialization; nested legacy models cannot mutate it.
    for output in stages:
        assert type(output).model_validate_json(output.model_dump_json()) == output
        assert type(output).model_json_schema()['properties']


def test_execution_performs_no_io_or_repository_lookup(monkeypatch):
    req_input, catalog = supplied(CASES['feasible'][0])
    expected = execute(req_input, catalog)
    def forbidden(*args, **kwargs):
        raise AssertionError('Electrical stage attempted external I/O or repository access')
    # All fixtures are loaded above. Both implicit fixture fallback and runtime DB
    # repositories are poisoned, as are ordinary file reads and transaction entry.
    from app.repositories.component_repository import ComponentRepository
    from app.services.requirement_engine import RequirementEngine
    from app.persistence import repositories
    from sqlalchemy.orm import Session
    for cls in (ComponentRepository, repositories.MemoryComponents, repositories.CatalogRepository):
        monkeypatch.setattr(cls, '__init__', forbidden)
    monkeypatch.setattr(RequirementEngine, '_load_templates', forbidden)
    monkeypatch.setattr(Session, 'execute', forbidden)
    monkeypatch.setattr(Session, 'begin', forbidden)
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    assert execute(req_input, catalog) == expected


def test_deep_immutability_and_finite_values():
    req_input, catalog = supplied(CASES['feasible'][0])
    before = req_input.model_dump_json(), catalog.model_dump_json()
    answers, rows = req_input.answers.read(), catalog.rows.read()
    answers['num_feeders'] = 1
    rows[0]['terminals'].clear()
    with pytest.raises(ValidationError):
        req_input.context.project_id = 'different'
    with pytest.raises(ValidationError):
        req_input.answers.data_json = '{}'
    assert before == (req_input.model_dump_json(), catalog.model_dump_json())
    selection = execute(req_input, catalog)[2]
    components = selection.components.read()
    components[0].terminals.clear()
    assert selection.components.read()[0].terminals
    for value in (float('nan'), float('inf'), -float('inf')):
        with pytest.raises((ValueError, ValidationError)):
            Snapshot[dict].capture({'nested': [value]})
        with pytest.raises((ValueError, ValidationError)):
            Snapshot[dict](data_json=json.dumps({'nested': [value]}))


def mapped_ids(stages):
    _, calc, selection, conn, _ = stages
    roles = {'component': [c.id for c in selection.components.read()],
             'module': [m.id for m in selection.modules.read()],
             'calculation': [c.id for c in calc.calculations.read()],
             'net': [n.id for n in conn.nets.read()],
             'connection': [c.id for c in conn.connections.read()]}
    # Reverse lexical IDs expose accidental sorting by document ID in the engines.
    return DocumentIdentities(bindings=tuple(IdentityBinding(namespace=kind, role=role,
        document_id=f'document:{kind}:{len(items)-index:03d}')
        for kind, items in roles.items() for index, role in enumerate(items)))


def test_document_bindings_preserve_topology_layout_and_references():
    case = CASES['feasible'][0]
    original = execute(*supplied(case))
    ids = mapped_ids(original)
    req_input, catalog = supplied(case, ids)
    mapped = execute(req_input, catalog)
    assert mapped == execute(req_input, catalog)
    for source, target in zip(original[2].components.read(), mapped[2].components.read()):
        assert target.id == ids.resolve('component', source.id)
        assert target.terminals == source.terminals
    for source, target in zip(original[2].modules.read(), mapped[2].modules.read()):
        assert target.id == ids.resolve('module', source.id)
        assert target.assigned_component_id == ids.resolve('component', source.assigned_component_id)
    for source, target in zip(original[3].connections.read(), mapped[3].connections.read()):
        assert target.id == ids.resolve('connection', source.id)
        assert target.net_id == ids.resolve('net', source.net_id)
        assert target.from_component == ids.resolve('component', source.from_component)
        assert target.to_component == ids.resolve('component', source.to_component)
        assert target.from_terminal == source.from_terminal
        assert target.to_terminal == source.to_terminal
    source, target = original[4].schematic.read(), mapped[4].schematic.read()
    for a, b in zip(source['symbols'], target['symbols']):
        assert b['id'] == ids.resolve('component', a['id'])
        assert (a['x'], a['y']) == (b['x'], b['y'])
    ports = {p['port_id'] for s in target['symbols'] for p in s['terminals']}
    for a, b in zip(source['wires'], target['wires']):
        assert b['id'] == b['conductor_id'] == ids.resolve('connection', a['id'])
        assert b['net_id'] == ids.resolve('net', a['net_id'])
        assert b['source_port_id'] in ports and b['target_port_id'] in ports
        assert a['waypoints'] == b['waypoints']
    # Feeder count/rating/labels are not identity inputs. Removed roles remain bound.
    smaller = execute(*supplied(case, ids, {'num_feeders': 8, 'incomer_rating': 160}))
    old = {c.id for c in mapped[2].components.read()}
    assert {c.id for c in smaller[2].components.read()} <= old


@pytest.mark.parametrize('overrides', [
    {'num_feeders': 4, 'incomer_rating': 100},
    {'neutral_required': False},
    {'num_feeders': 24},
])
def test_matches_existing_electrical_algorithms_at_boundaries(overrides):
    req_input, catalog = supplied(CASES['feasible'][0], overrides=overrides)
    _, calculations, selection, connectivity, schematic = execute(req_input, catalog)
    oracle = engine(CASES['feasible'][0])
    values = requirements_stage(req_input).values()
    expected_calc = oracle.calc_engine.calculate_db_parameters(values)
    assert calculations.calculations.read() == expected_calc
    expected_components = oracle.comp_selector.select_components(values['incomer_rating'], values['num_feeders'],
        values['phases'], values.get('neutral_required', values['phases'] == 3), expected_calc[2].value)
    assert selection.components.read() == expected_components
    expected_graph = oracle.graph_engine.build_electrical_graph(req_input.context.project_id, expected_components)
    expected_nets = oracle.netlist_engine.generate_netlist(expected_graph, expected_components,
        voltage=values['supply_voltage'], phases=values['phases'])
    assert connectivity.nets.read() == expected_nets
    assert schematic.schematic.read()['wires']


def test_pinned_versions_and_accepted_ratings_are_preserved():
    req_input, catalog = supplied(CASES['feasible'][0])
    rows = catalog.rows.read()
    for row in rows:
        row.update(component_version_id='component:'+row['id'], product_version_id='product:'+row['id'],
                   cad_model_version_id='model:'+row['id'])
    catalog = PinnedComponents(catalog_version='published-version', rows=Snapshot[list[dict]].capture(rows))
    selected = execute(req_input, catalog)[2].components.read()
    accepted = selected[0].model_copy(update={'current_rating': 300, 'name': 'Accepted incomer'})
    result = execute(req_input, catalog, Snapshot[list[ComponentRef]].capture([accepted]))
    assert result[2].components.read()[0] == accepted
    assert all(c.component_version_id == 'component:'+c.catalog_id for c in result[2].components.read())
    bad = accepted.model_copy(update={'component_version_id': 'latest'})
    with pytest.raises(DesignError, match='version differs'):
        execute(req_input, catalog, Snapshot[list[ComponentRef]].capture([bad]))


def test_explicit_topology_preserved_and_invalid_references_rejected():
    req_input, catalog = supplied(CASES['feasible'][0])
    req, _, selection, conn, _ = execute(req_input, catalog)
    nets = conn.nets.read()
    nets[0].connections[0].cross_section_mm2 = 95
    intent = type(conn)(electrical_graph=conn.electrical_graph, nets=type(conn.nets).capture(nets),
        connections=type(conn.connections).capture([c for n in nets for c in n.connections]))
    inputs = ConnectivityInput(context=req_input.context, requirements=req, selection=selection, intent=intent)
    assert connectivity_stage(inputs) == intent
    broken = nets[0].connections[0]
    broken.to_terminal = 'MISSING'
    invalid = type(conn)(electrical_graph=conn.electrical_graph, nets=type(conn.nets).capture(nets),
        connections=type(conn.connections).capture([c for n in nets for c in n.connections]))
    with pytest.raises(DesignError) as error:
        connectivity_stage(inputs.model_copy(update={'intent': invalid}))
    assert error.value.code == 'INVALID_NETLIST'


@pytest.mark.parametrize('overrides,code', [({'num_feeders': 0}, 'INVALID_REQUIREMENTS'),
    ({'phases': 1, 'supply_voltage': 230, 'neutral_required': False}, 'NO_FEASIBLE_COMPONENT'),
    ({'num_feeders': 25}, 'NO_FEASIBLE_COMPONENT'), ({'incomer_rating': 630}, 'NO_FEASIBLE_COMPONENT')])
def test_reviewed_errors_preserved(overrides, code):
    req_input, catalog = supplied(CASES['feasible'][0], overrides=overrides)
    with pytest.raises(DesignError) as error:
        execute(req_input, catalog)
    assert error.value.code == code


def test_contract_versions_identity_collisions_and_ownership():
    req_input, catalog = supplied(CASES['feasible'][0])
    for cls, stage in ((RequirementsInput, 'requirements'), (CalculationsInput, 'calculations'),
                       (SelectionInput, 'selection'), (ConnectivityInput, 'connectivity'), (SchematicInput, 'schematic')):
        assert cls.model_fields['algorithm_version'].default == STAGE_REGISTRY.by_id[stage].algorithm_version
    with pytest.raises(ValidationError):
        RequirementsInput.model_validate({**req_input.model_dump(), 'algorithm_version': 'future'})
    for bindings in (
        [IdentityBinding(namespace='component', role='QF001', document_id='a'),
         IdentityBinding(namespace='component', role='QF002', document_id='a')],
        [IdentityBinding(namespace='component', role='QF001', document_id='PANEL_ROOT')],
    ):
        with pytest.raises(ValidationError):
            DocumentIdentities(bindings=tuple(bindings))
    collision = DocumentIdentities(bindings=(IdentityBinding(namespace='component', role='QF001', document_id='QF002'),))
    with pytest.raises(DesignError) as error:
        execute(*supplied(CASES['feasible'][0], collision))
    assert error.value.code == 'STAGE_IDENTITY_COLLISION'
    req = requirements_stage(req_input)
    with pytest.raises(DesignError) as error:
        calculations_stage(CalculationsInput(context=req_input.context.model_copy(update={'project_id': 'wrong'}),
                                             requirements=req))
    assert error.value.code == 'STAGE_IDENTITY_MISMATCH'


def test_supplied_rules_and_missing_catalog_are_used_without_fallback():
    req_input, catalog = supplied(CASES['feasible'][0])
    template = req_input.rules.template.read()
    question = next(q for q in template['questions'] if q['id'] == 'num_feeders')
    question['validation']['max'] = 8
    changed = req_input.model_copy(update={'rules': PinnedRules(
        archetype_version='fixture-db-1', rules_version='stricter-supplied-rule',
        template=Snapshot[dict].capture(template))})
    with pytest.raises(DesignError) as error:
        requirements_stage(changed)
    assert error.value.code == 'INVALID_REQUIREMENTS'
    assert any('8' in message for message in error.value.errors)
    rows = [row for row in catalog.rows.read() if row['category'] != 'SPD']
    missing = PinnedComponents(catalog_version='without-spd', rows=Snapshot[list[dict]].capture(rows))
    with pytest.raises(DesignError) as error:
        execute(req_input, missing)
    assert error.value.code == 'CATALOG_INCOMPLETE'
