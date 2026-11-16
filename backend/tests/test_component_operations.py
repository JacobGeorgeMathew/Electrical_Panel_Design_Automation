"""Exact catalog identities and confirmed dependency closures, including reopen."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.document_api import DocumentSave
from app.models.operations import OperationPreviewRequest
from app.persistence.assets import AssetStore
from app.persistence.operations import OperationBatchRepository, _prepare
from app.persistence.repositories import CatalogRepository, PersistenceError
from app.services.design_errors import DesignError
from app.services.document_service import DocumentService
from app.services.operations.components import allocated_ids
from app.services.operations.engineering import EngineeringChoices
from app.services.operations.registry import preview_operations
from tests.test_document_contract import document_fixture
from tests.test_operation_persistence import persisted_base, load, history


def command(base, kind, target, parameters):
    models = {'AddComponent': ['cem', 'pdm'], 'RemoveComponent': ['cem', 'pdm', 'schematic']}
    affected = models[kind]
    return OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()),
        document_id=base.document.document_id, base_sequence=base.document.document_sequence,
        expected_version=base.document.lock_version, base_revision_id=base.document.base_revision_id,
        operations=[dict(type=kind, operation_id=str(uuid4()), origin=dict(kind='MANUAL', actor_id='user'),
            target=target, parameters=parameters, preconditions=dict(
                snapshot_sha256=getattr(base.document.models, affected[0]).sha256,
                model_sha256={kind: (getattr(base.document.models, kind).sha256 if getattr(base.document.models, kind) else None)
                              for kind in affected}))]))


def add_request(base, row=None):
    if row is None:
        row = base.snapshots.cem.components[0].model_dump()
        row.update(code=row['catalog_id'], component_version_id='published-1', product_version_id='product-1')
    request = command(base, 'AddComponent', dict(panel_id=base.document.panel_id),
        dict(catalog_id=row['code'], component_version_id=row['component_version_id'],
            product_version_id=row.get('product_version_id'),
            terminal_intent='UNCONNECTED', terminal_ids=[t['id'] for t in row['terminals']],
            placement=dict(position_mm=dict(x=220, y=200.25, z=37.5), zone_name='DIN', rail_id='rail-1')))
    return request, EngineeringChoices(components={row['component_version_id']: row},
        products=frozenset({(row['component_version_id'], row['product_version_id'])}) if row.get('product_version_id') else frozenset())


def removal(base, confirm=False):
    request = command(base, 'RemoveComponent', dict(cem_component_id='QF001'), {})
    if confirm:
        preview = preview_operations(base, request)
        request.operations[0].parameters.confirmed_cascade = preview.consequences[str(request.operations[0].operation_id)]
    return request


def test_add_allocates_deterministic_catalog_owned_identities():
    base = document_fixture()
    before = deepcopy(base)
    request, choices = add_request(base)
    preview = preview_operations(base, request, choices)
    assert preview == preview_operations(base, request, choices)
    candidate = _prepare(base, request, choices).after
    electrical, physical = allocated_ids(request.operations[0])
    assert candidate.snapshots.cem.components[-1].id == electrical
    assert candidate.snapshots.cem.components[-1].component_version_id == 'published-1'
    assert candidate.snapshots.pdm.components[-1].id == physical
    assert candidate.snapshots.pdm.components[-1].cem_component_id == electrical
    assert candidate.snapshots.pdm.components[-1].terminals[0]['x'] == 229
    assert candidate.document.pins.catalog_versions['component:' + electrical] == 'published-1'
    assert candidate.snapshots.cem.connections == base.snapshots.cem.connections
    assert base == before


@pytest.mark.parametrize('failure', ['terminal', 'placement', 'version', 'product', 'rail', 'stale_model', 'rotated', 'thermal'])
def test_add_rejects_incomplete_or_stale_intent_atomically(failure):
    base = document_fixture()
    request, choices = add_request(base)
    op = request.operations[0]
    if failure == 'terminal': op.parameters.terminal_ids = ['other']
    elif failure == 'placement': op.parameters.placement.position_mm.x = 125.5
    elif failure == 'version': op.parameters.component_version_id = 'missing'
    elif failure == 'product': op.parameters.product_version_id = 'unpublished'
    elif failure == 'rail': op.parameters.placement.rail_id = None
    elif failure in ('rotated', 'thermal'):
        from app.models.document import SnapshotReference, snapshot_sha256
        if failure == 'rotated': base.snapshots.pdm.components[0].rotation_deg = 20
        else: base.snapshots.pdm.total_heat_loss_watts = 100
        base.document.models.pdm = SnapshotReference(sha256=snapshot_sha256(base.snapshots.pdm))
        op.preconditions.model_sha256['pdm'] = base.document.models.pdm.sha256
    else: op.preconditions.model_sha256['pdm'] = '0' * 64
    before = deepcopy(base)
    with pytest.raises((DesignError, PersistenceError)):
        _prepare(base, request, choices)
    assert base == before


def test_remove_requires_exact_reviewed_cascade_and_preserves_unrelated_items():
    base = document_fixture()
    request = removal(base)
    preview = preview_operations(base, request)
    assert preview.candidate == base and not preview.changes
    deps = preview.consequences[str(request.operations[0].operation_id)].dependencies
    assert deps['connections'] == ['N-PE-C01'] and deps['routes'] == ['route-1']
    assert deps['symbols'] == ['symbol-1'] and deps['wires'] == ['wire-1']
    with pytest.raises(PersistenceError, match='explicitly confirm'):
        _prepare(base, request)
    request.operations[0].parameters.confirmed_cascade = preview.consequences[str(request.operations[0].operation_id)]
    candidate = _prepare(base, request).after
    assert not candidate.snapshots.cem.components and not candidate.snapshots.cem.connections
    assert not candidate.snapshots.pdm.routes and not candidate.snapshots.pdm.ducts[0].route_ids
    assert [s.id for s in candidate.snapshots.schematic.symbols] == ['symbol-2']
    assert candidate.snapshots.cem.nets[0].id == 'N-PE'
    request.operations[0].parameters.confirmed_cascade.dependencies['connections'].append('unrelated')
    with pytest.raises(DesignError) as error:
        _prepare(base, request)
    assert error.value.code == 'OPERATION_CASCADE_CHANGED'


def test_remove_preserves_unrelated_conductor_and_descendant_cleanup():
    from app.models.document import SnapshotReference, snapshot_sha256
    from app.models.pdm import PanelAccessory
    from tests.test_schematic_operations import with_evidence
    base = with_evidence()
    other = base.snapshots.cem.components[-1].model_copy(deep=True)
    other.id = 'PE002'
    base.snapshots.cem.components.append(other)
    connection = base.snapshots.cem.connections[0].model_copy(deep=True)
    connection.id, connection.from_component, connection.from_terminal = 'unrelated', 'PE001', 'MAIN_PE'
    connection.to_component = 'PE002'
    base.snapshots.cem.connections.append(connection)
    base.snapshots.cem.nets[0].connections.append(connection.model_copy(deep=True))
    base.snapshots.pdm.accessories = [PanelAccessory(id=key, catalog_id='hardware', name=key,
        category='HARDWARE', parent_id=parent, position=dict(x=10, y=20, z=30), width=10, height=10, depth=10)
        for key, parent in [('child', 'PDM-QF001'), ('grandchild', 'child'), ('unrelated-hardware', 'ENCLOSURE')]]
    for kind in ('cem', 'pdm'):
        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))
    request = removal(base, True)
    deps = request.operations[0].parameters.confirmed_cascade.dependencies
    assert deps['connections'] == ['N-PE-C01'] and deps['accessories'] == ['child', 'grandchild']
    after = _prepare(base, request).after
    assert [c.id for c in after.snapshots.cem.connections] == ['unrelated']
    assert [a.id for a in after.snapshots.pdm.accessories] == ['unrelated-hardware']
    # A previously reviewed closure cannot authorize a newly dependent object.
    request.operations[0].parameters.confirmed_cascade.dependencies['accessories'].remove('grandchild')
    with pytest.raises(DesignError) as error:
        _prepare(base, request)
    assert error.value.code == 'OPERATION_CASCADE_CHANGED'


def test_ambiguous_parent_identity_requires_a_new_proposal():
    from app.models.document import SnapshotReference, snapshot_sha256
    base = document_fixture()
    base.snapshots.pdm.rails[0].id = base.snapshots.pdm.components[0].rail_id = 'PDM-QF001'
    base.document.models.pdm = SnapshotReference(sha256=snapshot_sha256(base.snapshots.pdm))
    with pytest.raises(DesignError) as error:
        preview_operations(base, removal(base))
    assert error.value.code == 'OPERATION_CASCADE_AMBIGUOUS'


def test_add_save_reopen_and_confirmed_remove_are_durable(postgres_database):
    key, base = persisted_base(postgres_database)
    with postgres_database.sessions() as session:
        row = CatalogRepository(session, AssetStore(postgres_database.settings.asset_root)).get_component('MCB_16A_1P_10KA')
    request, _ = add_request(base, row)
    receipt = OperationBatchRepository(postgres_database).commit(key, request, 'add')
    current = load(postgres_database, key)
    save = DocumentSave(document_id=current.document.document_id,
        expected_version=current.document.lock_version, expected_document_sequence=current.document.document_sequence,
        requirements=current.snapshots.requirements, configuration=current.document.configuration)
    DocumentService(postgres_database).save(key, save)
    reopened = DocumentService(postgres_database).load(key)
    assert reopened.model_dump(mode='json') == receipt['result']
    assert reopened.snapshots.cem.components[-1].component_version_id == row['component_version_id']
    assert reopened.document.pins.catalog_versions['component:' + reopened.snapshots.cem.components[-1].id] == row['component_version_id']
    OperationBatchRepository(postgres_database).commit(key, removal(reopened, True), 'remove')
    after = load(postgres_database, key)
    assert [c.id for c in after.snapshots.cem.components] == [reopened.snapshots.cem.components[-1].id]
    assert len(history(postgres_database, key)[0]) == 2
