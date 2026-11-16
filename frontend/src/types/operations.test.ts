import { describe, expect, it } from 'vitest';
import fixture from './fixtures/operation-preview-v1.json';
import type { OperationPreviewRequest } from './operations';

describe('operation preview contract', () => {
  it('retains IDs, units and pinned base in the shared request fixture', () => {
    // JSON imports widen string literals; the explicit contract below is checked
    // by TypeScript and compared to the same JSON that Pydantic validates.
    const request: OperationPreviewRequest = {
      batch_id: fixture.batch_id, document_id: fixture.document_id,
      base_sequence: 7, expected_version: 3, base_revision_id: null,
      operations: [{ operation_id: fixture.operations[0].operation_id,
        type: 'MoveComponent', origin: { kind: 'MANUAL', actor_id: 'local-user' },
        target: { cem_component_id: 'QF001', pdm_component_id: 'PDM-QF001' },
        preconditions: { snapshot_sha256: 'a'.repeat(64) },
        parameters: { position_mm: { x: 140, y: 200.25, z: 37.5 } }, affected_models: ['pdm'] }],
    };
    expect(request).toEqual(fixture);
  });
});
