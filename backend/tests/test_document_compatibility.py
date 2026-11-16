"""Pure compatibility proposals retain originals and never apply geometry."""
from copy import deepcopy

import pytest

from app.services.document_compatibility import overlay_proposal


@pytest.fixture
def revision():
    return dict(revision_id='revision-1', snapshot_sha256='a' * 64,
        manifest={'engine_version': 'old-engine', 'generator': {'version': 'old'},
                  'cad_model_versions': {'c1': 'geometry-1'}, 'validation_policy_version': 'strict-v1'},
        cem={'components': [{'id': 'c1'}]},
        pdm={'components': [{'id': 'p1', 'cem_component_id': 'c1',
                            'position': dict(x=10, y=20, z=30), 'rotation_deg': 0}]})


def evidence(revision):
    return overlay_proposal(revision, {}, {})['base']


def test_matching_base_proposes_absolute_move_without_mutation(revision):
    overlay = {'editorTransforms': {'c1': dict(x=12, y=23, z=30, rotation_deg=0)}}
    original = deepcopy((revision, overlay))
    proposal = overlay_proposal(revision, overlay, evidence(revision))
    assert proposal['status'] == 'REVIEW_REQUIRED'
    assert proposal['requires_explicit_acceptance']
    assert proposal['operations'] == [dict(type='MoveComponent', component_id='c1',
        pdm_component_id='p1', before=dict(x=10, y=20, z=30), after=dict(x=12, y=23, z=30))]
    assert (revision, overlay) == original
    proposal['legacy_overlay']['editorTransforms'].clear()
    assert overlay == original[1]


@pytest.mark.parametrize('field', ['revision_id', 'revision_sha256', 'cem_sha256',
                                  'pdm_sha256', 'manifest', 'coordinate_frame'])
def test_missing_or_changed_base_requires_explicit_resolution(revision, field):
    base = evidence(revision)
    base.pop(field)
    overlay = {'editorTransforms': {'c1': dict(x=99, y=20, z=30)}}
    proposal = overlay_proposal(revision, overlay, base)
    assert proposal['status'] == 'BLOCKED' and not proposal['operations']
    assert proposal['legacy_overlay'] == overlay
    assert any(item['item'] == 'base.' + field for item in proposal['blocked'])
    assert 'Explicitly select' in proposal['blocked'][0]['reason']


@pytest.mark.parametrize('component,transform', [
    ('unknown', dict(x=1, y=2, z=3)), ('c1', dict(x=float('nan'), y=2, z=3)),
    ('c1', dict(x=1, y=2, z=3, rotation_deg=90)), ('c1', dict(x=1, y=2)),
    ('c1', dict(x=True, y=2, z=3)), ('c1', dict(x=1, y=2, z=3, scale=2))])
def test_unsupported_transforms_are_itemized_and_retained(revision, component, transform):
    proposal = overlay_proposal(revision, {'editorTransforms': {component: transform}}, evidence(revision))
    assert proposal['status'] == 'BLOCKED' and not proposal['operations']
    assert proposal['blocked'][0]['item'] == component
    assert proposal['legacy_overlay']['editorTransforms'][component].keys() == transform.keys()


def test_schematic_and_unknown_fields_remain_recoverable(revision):
    overlay = {'schematicData': {'edges': [{'unknown': 'wire'}]}, 'oldField': [1, 2]}
    proposal = overlay_proposal(revision, overlay, evidence(revision))
    assert proposal['status'] == 'BLOCKED'
    assert {item['item'] for item in proposal['blocked']} == {'oldField', 'schematicData'}
    assert proposal['legacy_overlay'] == overlay


@pytest.mark.parametrize('field', ['cem_sha256', 'pdm_sha256', 'manifest', 'coordinate_frame'])
def test_changed_geometry_identity_versions_or_frame_block_conversion(revision, field):
    base = evidence(revision)
    base[field] = {'engine_version': 'different'} if field == 'manifest' else 'different'
    overlay = {'editorTransforms': {'c1': dict(x=11, y=20, z=30)}}
    proposal = overlay_proposal(revision, overlay, base)
    assert proposal['status'] == 'BLOCKED' and not proposal['operations']
    assert proposal['legacy_overlay'] == overlay


def test_proposal_endpoint_contract():
    from app.main import create_app
    schema = create_app().openapi()
    assert '/api/projects/{project_id}/compatibility-proposal' in schema['paths']
    request = schema['components']['schemas']['OverlayCompatibilityInput']
    assert set(request['required']) == {'expected_version', 'revision_id'}
    assert request['properties']['source']['enum'] == ['workspace', 'recovery', 'supplied']
