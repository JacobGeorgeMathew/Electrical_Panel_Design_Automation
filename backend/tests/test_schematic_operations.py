"""Presentation independence, topology evidence and atomic conductor changes."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.document import ResolvedDocument, SnapshotReference, snapshot_sha256
from app.models.operations import OperationPreviewRequest
from app.persistence.operations import OperationBatchRepository, _prepare
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError
from app.services.operations.registry import preview_operations
from tests.test_document_contract import document_fixture
from tests.test_operation_persistence import load, persisted_base


def schematic_command(base, kind, target, parameters):
    affected = ['cem', 'pdm', 'schematic'] if kind == 'ModifyElectricalConnection' else ['schematic']
    return OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()),
        document_id=base.document.document_id, base_sequence=base.document.document_sequence,
        expected_version=base.document.lock_version, base_revision_id=base.document.base_revision_id,
        operations=[dict(type=kind, operation_id=str(uuid4()), origin=dict(kind='MANUAL', actor_id='user'),
            target=target, parameters=parameters, preconditions=dict(
                snapshot_sha256=getattr(base.document.models, affected[0]).sha256,
                model_sha256={kind: (getattr(base.document.models, kind).sha256 if getattr(base.document.models, kind) else None)
                              for kind in affected} if len(affected) > 1 else {}))]))


def with_evidence(base=None):
    base = base or document_fixture()
    # Real electrical endpoint: the P2-T05 checker deliberately refuses edits
    # relying on the legacy virtual PE anchor, even with explicit phase roles.
    other = base.snapshots.cem.components[0].model_copy(deep=True)
    other.id, other.category = 'PE001', 'EARTH_BAR'
    other.terminals = [dict(id='MAIN_PE', x=10, y=0, z=10)]
    base.snapshots.cem.components.append(other)
    connection = base.snapshots.cem.connections[0]
    connection.to_component, connection.to_terminal = 'PE001', 'MAIN_PE'
    base.snapshots.cem.nets[0].connections = [connection.model_copy(deep=True)]
    base.snapshots.pdm.routes[0].to_component, base.snapshots.pdm.routes[0].to_terminal = 'PE001', 'MAIN_PE'
    base.snapshots.schematic.symbols[1].component_id = 'PE001'
    base.snapshots.schematic.symbols[1].pins[0].terminal_id = 'MAIN_PE'
    base.document.configuration['electrical_topology'] = dict(domains=[
        dict(component_id='QF001', terminal_id='OUT', supply_id='supply-1', role='PE'),
        dict(component_id='PE001', terminal_id='MAIN_PE', supply_id='supply-1', role='PE')])
    for kind in ('cem', 'pdm', 'schematic'):
        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))
    return base


def connection_request(base, action='REPLACE'):
    connection = base.snapshots.cem.connections[0]
    conductor = connection.model_dump(exclude={'id'})
    conductor.update(conductor_material='COPPER', cross_section_mm2=2.5, insulation_diameter_mm=4.0,
                     insulation_type='PVC', minimum_bend_radius_mm=12.0)
    return schematic_command(base, 'ModifyElectricalConnection', dict(connection_id=connection.id),
        dict(action=action, conductor=conductor if action != 'DELETE' else None, invalidated_route_ids=['route-1'],
             removed_net_ids=['N-PE'] if action == 'DELETE' else []))


def test_move_symbol_translates_pins_and_endpoints_without_touching_connectivity():
    base = document_fixture()
    request = schematic_command(base, 'MoveSymbol', dict(symbol_id='symbol-1'),
                                dict(position_mm=dict(x=220, y=160)))
    candidate = _prepare(base, request).after
    assert candidate.snapshots.cem == base.snapshots.cem
    assert candidate.snapshots.pdm == base.snapshots.pdm
    assert candidate.snapshots.schematic.symbols[0].pins[0].position.model_dump() == dict(x=270, y=230)
    assert candidate.snapshots.schematic.wires[0].waypoints[0].model_dump() == dict(x=270, y=230)
    assert candidate.document.dirty_stages == ['routes', 'cad', 'schematic']
    assert base.snapshots.schematic.symbols[0].position.x == 100


@pytest.mark.parametrize('kind,key', [('symbol', 'symbol-1'), ('wire', 'wire-1'), ('pin', 'pin-1')])
def test_label_edit_is_presentation_only(kind, key):
    base = document_fixture()
    candidate = _prepare(base, schematic_command(base, 'UpdateSchematicLabel', dict(kind=kind, id=key), dict(label='Reviewed label'))).after
    assert candidate.snapshots.cem == base.snapshots.cem
    assert candidate.snapshots.pdm == base.snapshots.pdm
    assert candidate.snapshots.schematic != base.snapshots.schematic


def test_crossing_cannot_become_junction_without_shared_terminal():
    base = document_fixture()
    with pytest.raises(DesignError) as error:
        _prepare(base, schematic_command(base, 'UpdateJunctionPresentation', dict(pin_id='pin-1'), dict(visible=True, label='crossing')))
    assert error.value.code == 'OPERATION_JUNCTION'
    assert base.snapshots.cem == document_fixture().snapshots.cem


@pytest.mark.parametrize('failure', ['unknown_terminal', 'wrong_class', 'missing_evidence', 'cross_phase', 'different_supply',
                                     'unconfirmed_route', 'ambiguous_pin', 'capacity'])
def test_invalid_connection_fails_atomically(failure):
    base = with_evidence()
    if failure == 'ambiguous_pin':
        pin = base.snapshots.schematic.symbols[0].pins[0].model_copy(deep=True)
        pin.id = 'duplicate-terminal-pin'
        base.snapshots.schematic.symbols[0].pins.append(pin)
        base.document.models.schematic = SnapshotReference(sha256=snapshot_sha256(base.snapshots.schematic))
    elif failure == 'capacity':
        base.snapshots.cem.components[0].terminals[0]['conductor_max_mm2'] = 1.5
        base.document.models.cem = SnapshotReference(sha256=snapshot_sha256(base.snapshots.cem))
    request = connection_request(base)
    op = request.operations[0]
    if failure == 'unknown_terminal': op.parameters.conductor.from_terminal = 'missing'
    elif failure == 'wrong_class': op.parameters.conductor.wire_class = 'POWER'
    elif failure == 'missing_evidence': base.document.configuration = {}
    elif failure == 'cross_phase': base.document.configuration['electrical_topology']['domains'][0]['role'] = 'L1'
    elif failure == 'different_supply': base.document.configuration['electrical_topology']['domains'][0]['supply_id'] = 'other'
    elif failure == 'unconfirmed_route': op.parameters.invalidated_route_ids = []
    before = deepcopy(base)
    with pytest.raises(DesignError):
        _prepare(base, request)
    assert base == before


def test_replace_and_delete_update_all_references_consistently():
    base = with_evidence()
    replacement = _prepare(base, connection_request(base)).after
    assert replacement.snapshots.cem.connections[0].cross_section_mm2 == 2.5
    assert replacement.snapshots.cem.nets[0].connections == replacement.snapshots.cem.connections
    assert not replacement.snapshots.pdm.routes and not replacement.snapshots.pdm.ducts[0].route_ids
    assert replacement.snapshots.schematic.wires[0].id == 'wire-1'
    deleted = _prepare(base, connection_request(base, 'DELETE')).after
    assert not deleted.snapshots.cem.connections and not deleted.snapshots.cem.nets
    assert not deleted.snapshots.schematic.wires and not deleted.snapshots.pdm.routes


def test_create_and_junction_presentation_preserve_terminal_connectivity():
    base = with_evidence()
    third = base.snapshots.cem.components[1].model_copy(deep=True)
    third.id = 'PE002'
    base.snapshots.cem.components.append(third)
    symbol = base.snapshots.schematic.symbols[1].model_copy(deep=True)
    symbol.id, symbol.component_id, symbol.pins[0].id = 'symbol-3', 'PE002', 'pin-3'
    base.snapshots.schematic.symbols.append(symbol)
    base.document.configuration['electrical_topology']['domains'].append(
        dict(component_id='PE002', terminal_id='MAIN_PE', supply_id='supply-1', role='PE'))
    for kind in ('cem', 'schematic'):
        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))
    request = connection_request(base)
    op = request.operations[0]
    op.target.connection_id, op.parameters.action = None, 'CREATE'
    op.parameters.invalidated_route_ids = []
    op.parameters.conductor.to_component = 'PE002'
    created = _prepare(base, request).after
    assert len(created.snapshots.cem.connections) == len(created.snapshots.schematic.wires) == 2
    junction = _prepare(created, schematic_command(created, 'UpdateJunctionPresentation',
        dict(pin_id='pin-1'), dict(visible=False, label='PE branch'))).after
    assert len(junction.snapshots.schematic.junctions) == 1
    assert junction.snapshots.cem == created.snapshots.cem
    # Graphical intersections alone add no conductor, even when wire paths coincide.
    assert len(junction.snapshots.cem.connections) == 2
    ResolvedDocument.model_validate(junction.model_dump(include={'document', 'snapshots'}))


def test_regeneration_is_explicit_proposal_and_preserves_manual_positions():
    base = document_fixture()
    request = schematic_command(base, 'RegenerateSchematic', dict(schematic_id='schematic-1'), {})
    with pytest.raises(DesignError, match='explicit proposal'):
        preview_operations(base, request)
    op = request.operations[0]
    op.origin.proposal_id, op.proposal_status = 'proposal-1', 'PROPOSED'
    preview = preview_operations(base, request)
    assert preview.candidate.snapshots.schematic.symbols == base.snapshots.schematic.symbols
    assert preview.candidate.snapshots.cem == base.snapshots.cem
    with pytest.raises(PersistenceError):
        _prepare(base, request)
    op.parameters.replace_manual_positions = True
    replaced = preview_operations(base, request).candidate
    assert replaced.snapshots.schematic.symbols[0].position != base.snapshots.schematic.symbols[0].position
    assert [s.id for s in replaced.snapshots.schematic.symbols] == ['symbol-1', 'symbol-2']


def test_regeneration_does_not_invent_an_unregistered_panel_interface():
    base = with_evidence()
    base.document.enclosure_interfaces = []
    request = schematic_command(base, 'RegenerateSchematic', dict(schematic_id='schematic-1'), {})
    request.operations[0].origin.proposal_id, request.operations[0].proposal_status = 'proposal-2', 'PROPOSED'
    result = preview_operations(base, request).candidate
    assert {s.component_id for s in result.snapshots.schematic.symbols} == {'QF001', 'PE001'}
    assert result.snapshots.cem == base.snapshots.cem


def test_schematic_and_connection_save_reopen(postgres_database):
    from app.persistence.documents import DocumentRepository
    from app.models.document_api import DocumentSave
    from app.services.document_service import DocumentService
    key, base = persisted_base(postgres_database)
    base = with_evidence(base)
    with postgres_database.sessions.begin() as session:
        DocumentRepository(session).store(base)
    repo = OperationBatchRepository(postgres_database)
    repo.commit(key, schematic_command(base, 'MoveSymbol', dict(symbol_id='symbol-1'), dict(position_mm=dict(x=300, y=160))), 'symbol')
    moved = load(postgres_database, key)
    assert moved.snapshots.cem == base.snapshots.cem
    receipt = repo.commit(key, connection_request(moved), 'connection')
    saved = load(postgres_database, key)
    DocumentService(postgres_database).save(key, DocumentSave(document_id=saved.document.document_id,
        expected_version=saved.document.lock_version, expected_document_sequence=saved.document.document_sequence,
        requirements=saved.snapshots.requirements, configuration=saved.document.configuration))
    assert load(postgres_database, key).model_dump(mode='json') == receipt['result']
    ResolvedDocument.model_validate({k: v for k, v in receipt['result'].items() if k != 'content_sha256'})
