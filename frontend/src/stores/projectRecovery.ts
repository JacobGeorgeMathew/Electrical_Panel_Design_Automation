import type { Checkpoint, RecoveryBaseDocument } from '../types/recovery';
export type { Checkpoint, RecoveryDocument } from '../types/recovery';
const key = (id: string) => `panelstudio:recovery:v1:${id}`;
export function readRecovery(id: string): Checkpoint | null {
  try { return parseRecovery(JSON.parse(localStorage.getItem(key(id)) || 'null'));
  } catch { return null; }
}
// Keep the original storage key so existing installations and unknown schemas
// retain their bytes. Compatibility is decided only on explicit Recover.
export function parseRecovery(value: any): Checkpoint | null {
  return value?.document?.requirements && value?.document?.configuration && value?.document?.workspace
    && typeof value.saved_at === 'string' && Number.isInteger(value.base_version) ? value : null;
}
export function compatibleRecovery(checkpoint: Checkpoint, version: number, revision: string | null,
  base: RecoveryBaseDocument | null): boolean {
  const d = checkpoint.document;
  if ((checkpoint.schema_version !== undefined && checkpoint.schema_version !== 2)
    || (d.schema_version !== undefined && d.schema_version !== 2)
    || (d.schema_version === 2 && d.baseDocument === undefined)
    || d.baseRevisionId !== revision) return false;
  if (d.baseDocument) return !!base && d.baseDocument.document_id === base.document_id
    && d.baseDocument.document_sequence === base.document_sequence
    && d.baseDocument.schema_version === base.schema_version;
  return checkpoint.base_version === version && !base;
}
export function writeRecovery(id: string, checkpoint: Checkpoint) { localStorage.setItem(key(id), JSON.stringify(checkpoint)); }
export function clearRecovery(id: string) { localStorage.removeItem(key(id)); }
