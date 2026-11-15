import { beforeEach, expect, it } from 'vitest';
import { compatibleRecovery, readRecovery, writeRecovery } from './projectRecovery';
import type { Checkpoint, RecoveryBaseDocument } from '../types/recovery';

const legacy: Checkpoint = { base_version: 2, saved_at: '2026-11-15T00:00:00Z',
  document: { requirements: { unfinished: '-' }, configuration: {}, workspace: {}, baseRevisionId: 'R1' } };
const base: RecoveryBaseDocument = { document_id: 'D1', document_sequence: 3, schema_version: '1.0.0' };
beforeEach(() => localStorage.clear());
it('reads existing checkpoints without changing their original bytes', () => {
  writeRecovery('p', legacy);
  expect(readRecovery('p')).toEqual(legacy);
  expect(compatibleRecovery(legacy, 2, 'R1', null)).toBe(true);
  expect(compatibleRecovery(legacy, 3, 'R1', null)).toBe(false);
});
it('fences versioned recovery by document identity, sequence, schema and revision', () => {
  const c = { ...legacy, schema_version: 2, recovery_sequence: 7,
    document: { ...legacy.document, schema_version: 2, baseDocument: base } };
  expect(compatibleRecovery(c, 99, 'R1', base)).toBe(true);
  for (const changed of [{ ...base, document_id: 'D2' }, { ...base, document_sequence: 4 }, null]) {
    expect(compatibleRecovery(c, 2, 'R1', changed)).toBe(false);
  }
  expect(compatibleRecovery(c, 2, 'R2', base)).toBe(false);
  writeRecovery('p', { ...c, schema_version: 99 });
  expect(compatibleRecovery(readRecovery('p')!, 2, 'R1', base)).toBe(false);
  expect(readRecovery('p')?.schema_version).toBe(99);
});
