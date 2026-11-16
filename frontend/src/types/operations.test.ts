import { describe, expect, it } from 'vitest';
import fixture from './fixtures/operation-preview-v1.json';
import type { OperationPreviewRequest } from './operations';
import commands from './fixtures/operation-commands-v1.json';
import type { Operation, HistoryRequest } from './operations';

type JsonShape<T> = T extends string ? string : T extends number ? number
  : T extends (infer Item)[] ? JsonShape<Item>[]
  : T extends object ? { [Key in keyof T]: JsonShape<T[Key]> } : T;
const sharedCommands: { preview: JsonShape<OperationPreviewRequest>; history: JsonShape<HistoryRequest> } = commands;

describe('operation preview contract', () => {
  it('shares catalog, multi-model, schematic and history commands with Pydantic', () => {
    const move: Operation = { type: 'MoveSymbol', operation_id: 'op-1', origin: { kind: 'MANUAL', actor_id: 'user' },
      preconditions: { snapshot_sha256: 'a'.repeat(64) }, target: { symbol_id: 'symbol-1' },
      parameters: { position_mm: { x: 200, y: 160 } }, affected_models: ['schematic'] };
    const history: HistoryRequest = { ...commands.history, action: 'UNDO', origin: { kind: 'MANUAL', actor_id: 'local-user' } };
    expect(sharedCommands.preview.operations).toHaveLength(7);
    expect(history).toEqual(commands.history);
    expect(move.parameters.position_mm).toEqual(commands.preview.operations[2].parameters.position_mm);
    expect(commands.preview.operations[5].parameters.conductor?.cross_section_mm2).toBe(2.5);
  });
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
