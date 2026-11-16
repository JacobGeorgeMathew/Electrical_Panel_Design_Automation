"""Synthetic E1–E3 topology expectations; no engineering approval asserted."""
from copy import deepcopy
import itertools
import json

import pytest
from pydantic import ValidationError

from app.models.cem import CanonicalEngineeringModel, ComponentRef, ConnectionRef, NetRef
from app.models.electrical_graph import ElectricalEdge, ElectricalGraphModel, ElectricalNode
from app.persistence.assets import canonical_json, content_hash
from app.services.component_selector import ComponentSelector
from app.services.design_errors import DesignError
from app.services.electrical_consistency import (
    ConnectivityProjection, ElectricalDomain, TerminalEquivalence, project_legacy_connectivity,
)
from app.services.graph_engine import GraphEngine
from app.services.netlist_engine import NetlistEngine


def component(key, terminals, category='TERMINAL'):
    return ComponentRef(id=key, catalog_id='synthetic', name=key, category=category,
        current_rating=16, breaking_capacity=10, poles=1, width=18, height=80,
        depth=60, mounting='DIN_RAIL', heat_loss=1, cad_model='synthetic',
        terminals=[{'id': terminal} for terminal in terminals])


def net(key, source, target, voltage=415):
    return NetRef(id=key, name=key, voltage_level=voltage, wire_class='POWER', connections=[
        ConnectionRef(id=key + '-C01', from_component=source[0], from_terminal=source[1],
            to_component=target[0], to_terminal=target[1], net_id=key)])


def board(components, nets):
    return CanonicalEngineeringModel(project_id='TEST', panel_id='DB', components=components,
        nets=nets, connections=[c.model_copy(deep=True) for n in nets for c in n.connections])


def all_domains(cem, role='L1'):
    return {(c.id, t['id']): ElectricalDomain(supply_id='S1', role=role)
            for c in cem.components for t in c.terminals}


def codes(result):
    return {i.code for i in result.issues}


@pytest.fixture
def shared_busbar():
    # E1: four real conductors, three at one screw. The breaker remains a
    # boundary even when both sides have the same supply/phase classification.
    return board([
        component('QF001', ['L1_OUT'], 'MCCB'),
        component('BUS001', ['IN_L1'], 'BUSBAR'),
        component('SPD001', ['L1'], 'SPD'),
        component('QF002', ['IN', 'OUT'], 'MCB'),
        component('X001', ['LEFT']),
    ], [
        net('NET-MAIN-L1', ('QF001', 'L1_OUT'), ('BUS001', 'IN_L1')),
        net('NET-SPD-L1', ('BUS001', 'IN_L1'), ('SPD001', 'L1')),
        net('NET-BRANCH-QF002-L1-IN', ('BUS001', 'IN_L1'), ('QF002', 'IN'), 239.6003617136947),
        net('NET-BRANCH-QF002-L1-OUT', ('QF002', 'OUT'), ('X001', 'LEFT'), 239.6003617136947),
    ])


def test_shared_screw_is_one_equipotential_with_three_distinct_conductors(shared_busbar):
    result = project_legacy_connectivity(shared_busbar, domains=all_domains(shared_busbar))
    result.require_consistent()
    assert result.status == 'PASS'  # Bounded topology only.
    assert len(result.groups) == 2
    inputs = next(g for g in result.groups if ('QF002', 'IN') in g.terminals)
    outputs = next(g for g in result.groups if ('QF002', 'OUT') in g.terminals)
    assert inputs.net_id == 'NET-BRANCH-QF002-L1-IN'
    assert inputs.legacy_net_ids == ('NET-BRANCH-QF002-L1-IN', 'NET-MAIN-L1', 'NET-SPD-L1')
    assert len(inputs.conductor_ids) == 3 and len(outputs.conductor_ids) == 1
    assert set(inputs.terminals).isdisjoint(outputs.terminals)
    assert sorted(c for g in result.groups for c in g.conductor_ids) == sorted(c.id for c in shared_busbar.connections)
    assert {n.voltage_level for n in result.legacy_nets} == {415, 239.6003617136947}
    assert ConnectivityProjection.model_validate_json(result.model_dump_json()) == result


def test_legacy_snapshot_bytes_hashes_and_net_references_are_preserved(shared_busbar, tmp_path):
    path = tmp_path / 'legacy.json'
    raw = json.dumps(shared_busbar.model_dump(mode='json'), indent=3).encode()
    path.write_bytes(raw)
    loaded = CanonicalEngineeringModel.model_validate_json(raw)
    before = loaded.model_dump_json(), canonical_json(loaded.model_dump()), content_hash(loaded.model_dump())
    project_legacy_connectivity(loaded, domains=all_domains(loaded))
    assert path.read_bytes() == raw
    assert before == (loaded.model_dump_json(), canonical_json(loaded.model_dump()), content_hash(loaded.model_dump()))
    assert loaded == shared_busbar


def test_distinct_screws_need_explicit_equivalence_and_do_not_create_a_conductor():
    cem = board([component('BUS', ['IN_L1', 'TAP_L1', 'IN_L2', 'IN_N'], 'BUSBAR')], [])
    domains = {('BUS', key): ElectricalDomain(supply_id='S1', role=role) for key, role in
               [('IN_L1', 'L1'), ('TAP_L1', 'L1'), ('IN_L2', 'L2'), ('IN_N', 'N')]}
    group = TerminalEquivalence(id='EQ-L1', members=(('BUS', 'IN_L1'), ('BUS', 'TAP_L1')),
                               evidence_id='SYNTHETIC-REVIEW-GROUP-v1')
    separate = project_legacy_connectivity(cem, domains=domains)
    assert len(separate.groups) == 4
    common = project_legacy_connectivity(cem, domains=domains, equivalences=[group])
    assert common.status == 'PASS' and len(common.groups) == 3
    assert all(not g.conductor_ids for g in common.groups)
    assert all(g.net_id is None for g in common.groups)
    missing = project_legacy_connectivity(cem, domains=domains,
        equivalences=[group.model_copy(update={'evidence_id': None})])
    assert missing.status == 'UNRESOLVED' and len(missing.groups) == 4
    assert 'MISSING_EQUIVALENCE_EVIDENCE' in codes(missing)


@pytest.mark.parametrize('left,right', list(itertools.combinations(['L1', 'L2', 'L3', 'N', 'PE'], 2)))
@pytest.mark.parametrize('kind', ['conductor', 'equivalence'])
def test_incompatible_domain_truth_table_rejects_without_mutation(left, right, kind):
    cem = board([component('BUS', ['A', 'B'], 'BUSBAR')],
                [net('N', ('BUS', 'A'), ('BUS', 'B'), 0)] if kind == 'conductor' else [])
    domains = {('BUS', 'A'): ElectricalDomain(supply_id='S1', role=left),
               ('BUS', 'B'): ElectricalDomain(supply_id='S1', role=right)}
    equivalences = [TerminalEquivalence(id='E', members=(('BUS', 'A'), ('BUS', 'B')),
                                       evidence_id='synthetic')] if kind == 'equivalence' else []
    before = deepcopy(cem)
    result = project_legacy_connectivity(cem, domains=domains, equivalences=equivalences)
    expected = 'PE_BOUNDARY_CONFLICT' if 'PE' in (left, right) else 'PHASE_DOMAIN_CONFLICT'
    assert expected in codes(result) and result.status == 'FAIL'
    assert result.groups == result.legacy_nets == ()
    with pytest.raises(DesignError) as error:
        result.require_consistent(require_resolved=False)
    assert error.value.code == 'ELECTRICAL_INCONSISTENCY'
    assert expected in error.value.as_dict()['error']['errors'][0]
    assert cem == before


def test_transitive_conflict_is_detected_through_unknown_middle_domain():
    cem = board([component('BUS', ['A', 'B', 'C'], 'BUSBAR')],
        [net('N1', ('BUS', 'A'), ('BUS', 'B')), net('N2', ('BUS', 'B'), ('BUS', 'C'))])
    domains = {('BUS', 'A'): ElectricalDomain(supply_id='S1', role='L1'),
               ('BUS', 'C'): ElectricalDomain(supply_id='S1', role='L2')}
    result = project_legacy_connectivity(cem, domains=domains)
    assert {'PHASE_DOMAIN_CONFLICT', 'MISSING_TERMINAL_DOMAIN'} <= codes(result)
    assert result.status == 'FAIL' and not result.groups
    domains[('BUS', 'C')] = ElectricalDomain(supply_id='S2', role='L1')
    assert 'SUPPLY_DOMAIN_CONFLICT' in codes(project_legacy_connectivity(cem, domains=domains))


@pytest.mark.parametrize('category', ['MCB', 'MCCB', 'SPD', 'LOAD'])
def test_functional_device_paths_are_not_permanent_equivalences(category):
    cem = board([component('DEVICE', ['IN', 'OUT'], category)], [])
    eq = TerminalEquivalence(id='E', members=(('DEVICE', 'IN'), ('DEVICE', 'OUT')), evidence_id='synthetic')
    result = project_legacy_connectivity(cem, domains=all_domains(cem), equivalences=[eq])
    assert 'UNSUPPORTED_PERMANENT_GROUP' in codes(result)


def test_functional_graph_and_equal_coordinates_never_join_terminals():
    cem = board([component('A', ['T']), component('B', ['T'])], [])
    for c in cem.components:
        c.terminals[0].update(x=10, y=20, label='L1')
    cem.electrical_graph = ElectricalGraphModel(project_id=cem.project_id,
        nodes=[ElectricalNode(id=c.id, name=c.name, type=c.category, category=c.category) for c in cem.components],
        edges=[ElectricalEdge(source='A', target='B', relation='FEEDS')])
    result = project_legacy_connectivity(cem, domains=all_domains(cem))
    assert len(result.groups) == 2 and all(not g.conductor_ids for g in result.groups)
    cem.electrical_graph.edges[0].target = 'ORPHAN'
    assert 'UNKNOWN_GRAPH_ENDPOINT' in codes(project_legacy_connectivity(cem))


@pytest.mark.parametrize('fault,expected', [
    ('component', 'UNKNOWN_COMPONENT'), ('terminal', 'UNKNOWN_TERMINAL'),
    ('duplicate_connection', 'DUPLICATE_CONNECTION_ID'), ('duplicate_component', 'DUPLICATE_COMPONENT_ID'),
    ('duplicate_terminal', 'DUPLICATE_TERMINAL_ID'), ('duplicate_net', 'DUPLICATE_NET_ID'),
    ('flat_content', 'CONNECTION_PROJECTION_MISMATCH'), ('flat_missing', 'CONNECTION_PROJECTION_MISMATCH'),
    ('flat_duplicate', 'DUPLICATE_FLAT_CONNECTION_ID'), ('net_reference', 'CONNECTION_NET_MISMATCH'),
    ('self', 'SELF_CONNECTION'), ('nonfinite', 'NONFINITE_LEGACY_VOLTAGE'), ('empty_net', 'EMPTY_NET'),
    ('invalid_terminal', 'INVALID_TERMINAL_ID'), ('unknown_domain_terminal', 'UNKNOWN_TERMINAL'),
    ('invalid_domain', 'INVALID_DOMAIN'), ('unsupported_panel', 'UNSUPPORTED_PANEL_TYPE'),
])
def test_identity_and_reference_failures(shared_busbar, fault, expected):
    cem = shared_busbar
    domains = all_domains(cem)
    c = cem.nets[0].connections[0]
    if fault == 'component': c.from_component = 'MISSING'
    elif fault == 'terminal': c.from_terminal = 'MISSING'
    elif fault == 'duplicate_connection': cem.nets[1].connections[0].id = c.id
    elif fault == 'duplicate_component': cem.components.append(cem.components[0].model_copy(deep=True))
    elif fault == 'duplicate_terminal': cem.components[0].terminals *= 2
    elif fault == 'duplicate_net': cem.nets.append(cem.nets[0].model_copy(deep=True))
    elif fault == 'flat_content': cem.connections[0].cross_section_mm2 = 2.5
    elif fault == 'flat_missing': cem.connections.pop()
    elif fault == 'flat_duplicate': cem.connections.append(cem.connections[0].model_copy(deep=True))
    elif fault == 'net_reference': c.net_id = 'WRONG'
    elif fault == 'self': c.to_component, c.to_terminal = c.from_component, c.from_terminal
    elif fault == 'nonfinite': cem.nets[0].voltage_level = float('nan')
    elif fault == 'empty_net': cem.nets[0].connections = []
    elif fault == 'invalid_terminal': cem.components[0].terminals[0]['id'] = []
    elif fault == 'unknown_domain_terminal': domains[('BUS001', 'MISSING')] = ElectricalDomain(supply_id='S1', role='L1')
    elif fault == 'invalid_domain': domains[('BUS001', 'IN_L1')] = {'supply_id': 'S1', 'role': 'L1'}
    elif fault == 'unsupported_panel': cem.panel_type = 'MCC'
    result = project_legacy_connectivity(cem, domains=domains)
    assert expected in codes(result) and result.status == 'FAIL' and not result.groups


def test_disconnected_legacy_net_never_shortcuts_conductor_closure():
    cem = board([component('T', ['A', 'B', 'C', 'D'])],
                [net('N', ('T', 'A'), ('T', 'B')), net('other', ('T', 'C'), ('T', 'D'))])
    second = cem.nets.pop().connections[0]
    second.net_id = 'N'
    cem.nets[0].connections.append(second)
    cem.connections = deepcopy(cem.nets[0].connections)
    result = project_legacy_connectivity(cem, domains=all_domains(cem))
    assert len(result.groups) == 2
    assert [g.net_id for g in result.groups] == ['N', None]
    assert 'LEGACY_NET_SPLIT' in codes(result)


def test_parallel_conductors_keep_distinct_identities(shared_busbar):
    c = shared_busbar.nets[0].connections[0].model_copy(update={'id': 'PARALLEL'})
    shared_busbar.nets[0].connections.append(c)
    shared_busbar.connections.append(c.model_copy(deep=True))
    result = project_legacy_connectivity(shared_busbar, domains=all_domains(shared_busbar))
    assert result.status == 'PASS'
    assert sum(len(g.conductor_ids) for g in result.groups) == 5


@pytest.mark.parametrize('feeders,rating', [(4, 100), (8, 250), (12, 250), (16, 250)])
def test_existing_generated_db_topology_remains_representable(feeders, rating):
    phases = 3  # The current published prototype catalog supports 3P incomers.
    components = ComponentSelector().select_components(rating, feeders, phases, True, rating * 1.25)
    graph = GraphEngine().build_electrical_graph('TEST', components)
    nets = NetlistEngine().generate_netlist(graph, components, phases=phases)
    cem = board(components, nets)
    cem.electrical_graph = graph
    before = canonical_json(cem.model_dump())
    result = project_legacy_connectivity(cem)
    assert result.status == 'UNRESOLVED'
    assert codes(result) == {'MISSING_TERMINAL_DOMAIN', 'VIRTUAL_PE_ANCHOR'}
    assert sum(len(g.conductor_ids) for g in result.groups) == len(cem.connections)
    assert len({c for g in result.groups for c in g.conductor_ids}) == len(cem.connections)
    assert canonical_json(cem.model_dump()) == before
    with pytest.raises(DesignError): result.require_consistent()
    result.require_consistent(require_resolved=False)  # historical preview only


def test_virtual_root_is_limited_to_legacy_earth_endpoint():
    cem = board([component('PEBAR', ['MAIN_PE'], 'EARTH_BAR')],
                [net('PE', ('PANEL_ROOT', 'EARTH_STUD'), ('PEBAR', 'MAIN_PE'), 0)])
    domains = all_domains(cem, 'PE')
    domains[('PANEL_ROOT', 'EARTH_STUD')] = ElectricalDomain(supply_id='S1', role='L1')
    assert 'PE_BOUNDARY_CONFLICT' in codes(project_legacy_connectivity(cem, domains=domains))
    cem.nets[0].connections[0].from_terminal = 'ANY_OTHER_PORT'
    cem.connections = deepcopy(cem.nets[0].connections)
    assert 'UNKNOWN_COMPONENT' in codes(project_legacy_connectivity(cem))


def test_projection_and_errors_are_invariant_under_input_order(shared_busbar):
    domains = all_domains(shared_busbar)
    expected = project_legacy_connectivity(shared_busbar, domains=domains)
    shared_busbar.components.reverse()
    shared_busbar.nets.reverse()
    shared_busbar.connections.reverse()
    assert project_legacy_connectivity(shared_busbar, domains=dict(reversed(list(domains.items())))) == expected
    domains[('SPD001', 'L1')] = ElectricalDomain(supply_id='S2', role='PE')
    bad = project_legacy_connectivity(shared_busbar, domains=domains)
    shared_busbar.components.reverse()
    shared_busbar.nets.reverse()
    assert project_legacy_connectivity(shared_busbar, domains=domains) == bad


@pytest.mark.parametrize('fields', [{'supply_id': '', 'role': 'L1'}, {'supply_id': '  ', 'role': 'L1'},
                                  {'supply_id': 'S1', 'role': 'POWER'}, {'supply_id': 'S1', 'role': 'PEN'},
                                  {'supply_id': 'S1', 'role': 'L1', 'extra': True}])
def test_explicit_domain_contract_rejects_ambiguous_values(fields):
    with pytest.raises(ValidationError): ElectricalDomain.model_validate(fields)


@pytest.mark.parametrize('fault,expected', [
    ('duplicate', 'DUPLICATE_EQUIVALENCE_ID'), ('member', 'DUPLICATE_EQUIVALENCE_MEMBER'),
    ('dangling', 'UNKNOWN_TERMINAL'), ('bridge', 'UNSUPPORTED_PERMANENT_GROUP'),
    ('phase_without_evidence', 'PHASE_DOMAIN_CONFLICT'),
])
def test_invalid_equivalence_evidence_cannot_authorize_partial_partition(fault, expected):
    cem = board([component('BUS', ['A', 'B'], 'BUSBAR'), component('OTHER', ['T'])], [])
    domains = all_domains(cem)
    members = (('BUS', 'A'), ('BUS', 'B'))
    if fault == 'member': members = (('BUS', 'A'), ('BUS', 'A'))
    elif fault == 'dangling': members = (('BUS', 'A'), ('BUS', 'ORPHAN'))
    elif fault == 'bridge': members = (('BUS', 'A'), ('OTHER', 'T'))
    elif fault == 'phase_without_evidence': domains[('BUS', 'B')] = ElectricalDomain(supply_id='S1', role='L2')
    eq = TerminalEquivalence(id='EQ', members=members,
        evidence_id=None if fault == 'phase_without_evidence' else 'synthetic')
    result = project_legacy_connectivity(cem, domains=domains,
        equivalences=[eq, eq] if fault == 'duplicate' else [eq])
    assert expected in codes(result) and result.status == 'FAIL' and not result.groups


def test_identities_are_not_trimmed_or_reallocated():
    cem = board([component(' A ', [' T ']), component('B', ['T'])],
                [net(' N ', (' A ', ' T '), ('B', 'T'))])
    result = project_legacy_connectivity(cem, domains=all_domains(cem))
    assert result.groups[0].net_id == ' N '
    assert (' A ', ' T ') in result.groups[0].terminals
    assert result.groups[0].conductor_ids == (' N -C01',)
